from dotenv import load_dotenv
from common import *

import uuid
import os


unique_id = str(uuid.uuid4())



load_dotenv()
MACHINE_NAME = os.getenv('MACHINE_NAME')


class RelatorioPPT():
    def __init__(self, agent_number, retry_count, disc_message_id, message_json):
        self.qvd_path           = Path('G:/Drives compartilhados/Ambiente de Produção/_QVD')
        self.download_path      = Path.cwd().joinpath(f'downloads/raw_files/agent{agent_number}/')
        self.ready_path         = Path.cwd().joinpath(f'downloads/ready_files/agent{agent_number}/')
        self.script_path        = get_path_script_qvs(self.qvd_path, agent_number)

        self.disc_message_id    = disc_message_id
        self.mj                 = message_json
        self.agent_number       = agent_number
        self.retry_count        = retry_count


    def __discord_message(self, message):
        message_data = {
            'message_id': self.disc_message_id,
            'user_id': f'<@{self.mj["discord_user_id"]}>',
            'company': self.mj['company_name'],
            'type_process': 'Relatório PPT',
            'english': 'Inglês' if self.mj['narrative'] else 'Português',
            'stage': message,
            'footer': self.mj['created_at']
        }
        publish_message_discord(message_data)


    def __clear_download_path(self):
        self.__discord_message('organizando as pastas')
        for file in self.download_path.rglob('*.*'):
            file.unlink()


    def __organize_environment(self):
        self.__discord_message('editando script do qlik')
        self.gestao_pos = has_gestao_pos(self.mj['company_name'])
        edit_script_qvs(
            script_path=self.script_path,
            company_name=self.mj['company_name'],
            narrative=self.mj['narrative'],
            month_analysis=self.mj['month_analysis'],
            gestao_pos=self.gestao_pos
        )

    def __init_browser(self):
        self.__discord_message('abrindo navegador')
        self.driver = init_browser(self.download_path)
        self.wait = WebDriverWait(self.driver, 60)


    def __control_qlik(self):
        navigate_to_process(self.driver, self.wait, self.agent_number)
        self.__discord_message('aguardando qlik processar a operadora')
        process_company(self.driver)
        self.__discord_message('aguardando qlik exportar o ppt')
        return navigate_to_export(self.driver, self.wait, self.mj['narrative'], self.gestao_pos)


    def __manager_qlik_and_move_to_drive(self):
        download_success = self.__control_qlik()
        if download_success:
            wait_until_download_finish(self.download_path, self.driver)
            company_pretty_name, audit_date, suridata_product = get_pretty_name(self.mj['company_name'])
            is_audith = need_audith(self.mj['audith'], company_pretty_name, audit_date, suridata_product)
            self.__discord_message('esperando suripoint processar o arquivo')
            if move_to_drive(self.qvd_path, self.mj['company_name'], is_audith, self.download_path, self.mj['narrative'], company_pretty_name):
                self.__discord_message('relatório salvo no drive :white_check_mark:')
                return True
            else:
                self.__discord_message('erro no suripoint ❌')
        else:
            self.__discord_message('erro no qlik ❌')
        
        return False


    def run(self):
        self.__clear_download_path()
        self.__organize_environment()
        self.__init_browser()
        return self.__manager_qlik_and_move_to_drive()
