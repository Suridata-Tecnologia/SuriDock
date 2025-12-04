from extensions.suridata_api import SuridataApi
from extensions.trello       import Trello
from common import *



class Sentinel():
    def __init__(self, agent_number, retry_count, disc_message_id, message_json, pretty_name):
        self.qvd_path           = Path('G:/Drives compartilhados/Ambiente de Produção/_QVD')
        self.script_path        = get_path_script_qvs(self.qvd_path, agent_number, sentinel=True)

        self.disc_message_id    = disc_message_id
        self.mj                 = message_json
        self.agent_number       = agent_number
        self.retry_count        = retry_count
        self.pretty_name        = pretty_name
        self.mj['company_name'] = SuridataApi().get_company_by_id(self.mj['company_id'])['drive_folder']


    def __discord_message(self, message, progress, status='running'):
        message_data = {
            'message_id': self.disc_message_id,
            'discord_username': self.mj['discord_username'],
            'company': self.mj['company_name'],
            'type_process': self.pretty_name,
            'stage': message,
            'progress': progress,
            'status': status,
            'footer': self.mj['created_at']
        }
        publish_message_discord(message_data)


    def __organize_environment(self):
        self.__discord_message('Editando script do qlik', 0)
        edit_script_qvs(
            script_path=self.script_path,
            company_name=self.mj['company_name'],
            narrative=False,
            month_analysis='não',
            gestao_pos=False,
            sentinel=True
        )


    def __init_browser(self):
        self.__discord_message('Abrindo navegador', 25)
        self.driver = init_browser()
        self.wait = WebDriverWait(self.driver, 60)

    
    def __control_qlik(self):
        self.__discord_message('Navegando entre as páginas do qlik', 50)
        navigate_to_process(self.driver, self.wait, self.agent_number)
        self.__discord_message('Aguardando qlik processar a operadora', 75)
        if not process_company(self.driver):
            Trello(card_id=self.mj['trello_card_id'], list_target_name='Operação: Erros').run()
            self.__discord_message('Erro no qlik', 0, status='error')
            return False
        
        self.driver.quit()
        Trello(card_id=self.mj['trello_card_id'], list_target_name='Operação: Validação').run()
        self.__discord_message('Processo finalizado com sucesso', 100, status='success')
        return True


    def run(self):
        self.__organize_environment()
        self.__init_browser()
        self.__control_qlik()