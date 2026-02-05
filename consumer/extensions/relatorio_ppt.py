from extensions.suridata_api    import SuridataApi
from dotenv                     import load_dotenv
from extensions.trello          import Trello
from common                     import *

import os



load_dotenv()
MACHINE_NAME = os.getenv('MACHINE_NAME')


class RelatorioPPT():
    def __init__(self, agent_number, retry_count, disc_message_id, message_json, pretty_name):
        self.qvd_path           = Path('G:/Drives compartilhados/Ambiente de Produção/_QVD')
        self.download_path      = Path.cwd().joinpath(f'downloads/raw_files/agent{agent_number}/')
        self.ready_path         = Path.cwd().joinpath(f'downloads/ready_files/agent{agent_number}/')
        self.script_path        = get_path_script_qvs(self.qvd_path, agent_number)

        self.disc_message_id    = disc_message_id
        self.mj                 = message_json
        self.agent_number       = agent_number
        self.retry_count        = retry_count
        self.pretty_name        = pretty_name

        if not self.mj['company_name']:
            self.mj['company_name'] = SuridataApi().get_company_by_id(self.mj['company_id'])['drive_folder']


    def __discord_message(self, message, progress, status='running', discord_channel='bots'):
        message_data = {
            'discord_channel': discord_channel,
            'message_id': self.disc_message_id,
            'discord_username': self.mj['discord_username'],
            'company': self.mj['company_name'],
            'type_process': self.pretty_name,
            'english': 'Inglês' if self.mj['narrative'] else 'Português',
            'stage': message,
            'progress': progress,
            'status': status,
            'footer': self.mj['created_at']
        }
        publish_message_discord(message_data)


    def __clear_download_path(self):
        self.__discord_message('organizando as pastas', 0)
        for file in self.download_path.rglob('*.*'):
            file.unlink()


    def __organize_environment(self):
        self.__discord_message('editando script do qlik', 16)
        self.__move_card_trello('Saúde: Processando PPT') # coluna de quando o processo inicia
        self.gestao_pos = has_gestao_pos(self.mj['company_name'])
        edit_script_qvs(
            script_path=self.script_path,
            company_name=self.mj['company_name'],
            narrative=self.mj['narrative'],
            month_analysis=self.mj['month_analysis'],
            gestao_pos=self.gestao_pos
        )

    def __init_browser(self):
        self.__discord_message('abrindo navegador', 32)
        self.driver = init_browser(self.download_path)
        self.wait = WebDriverWait(self.driver, 60)


    def __control_qlik(self):
        navigate_to_process(self.driver, self.wait, self.agent_number)
        self.__discord_message('aguardando qlik processar a operadora', 48)
        if not process_company(self.driver):
            return False
        self.__discord_message('aguardando qlik exportar o ppt', 64)
        return navigate_to_export(self.driver, self.wait, self.mj['narrative'], self.gestao_pos)
    

    def __move_card_trello(self, list_target_name):
        if self.mj['trello_card_id']:
            Trello(card_id=self.mj['trello_card_id'], list_target_name=list_target_name).run()


    def __manager_qlik_and_move_to_drive(self):
        if self.__control_qlik():
            wait_until_download_finish(self.download_path, self.driver)
            company_pretty_name, audit_date, suridata_product = get_pretty_name(self.mj['company_name'])
            is_audith = need_audith(self.mj['audith'], company_pretty_name, audit_date, suridata_product)
            self.__discord_message('esperando suripoint processar o arquivo', 80)
            if move_to_drive(self.qvd_path, self.mj['company_name'], is_audith, self.download_path, self.mj['narrative'], company_pretty_name):
                self.__discord_message('relatório salvo no drive', 100, 'success')
                self.__move_card_trello('Saúde: Gerar ppt + 1ª validação') # coluna de quando o processo é finalizado com sucesso
                return True
            else:
                self.__discord_message('erro no suripoint', 0, 'error')
        else:
            self.__discord_message('erro no qlik', 0, 'error')
        
        self.__move_card_trello('Saúde: Review') # coluna de quando o processo falha
        return False


    def run(self):
        self.__clear_download_path()
        self.__organize_environment()
        self.__init_browser()
        return self.__manager_qlik_and_move_to_drive()
