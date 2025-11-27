from dotenv import load_dotenv
from common import *

import os



load_dotenv()
MACHINE_NAME = os.getenv('MACHINE_NAME')


class RelatorioPPT():
    def __init__(self, agent_number, retry_count, body_message):
        self.qvd_path           = Path('G:/Drives compartilhados/Ambiente de Produção/_QVD')
        self.download_path      = Path(f'downloads/raw_files/agent{agent_number}/')
        self.ready_path         = Path(f'downloads/ready_files/agent{agent_number}/')

        self.agent_number       = agent_number
        self.retry_count        = retry_count

        itens_list              = body_message.split(' ## ')
        self.type_proccess      = itens_list[0]
        self.created_at         = itens_list[1]
        self.company_name       = itens_list[2]
        self.discord_user_id    = itens_list[3]
        self.discord_message_id = itens_list[4]
        self.trello_card_id     = itens_list[5]
        self.activity           = itens_list[6]
        self.month_analysis     = itens_list[7]
        self.audith             = itens_list[8]
        self.narrative          = itens_list[9]
        self.user_email         = itens_list[10]
        self.mail_list          = itens_list[11]

        self.script_path        = get_path_script_qvs(self.qvd_path, self.agent_number)


    def __discord_message(self, message):
        publish_message_discord(message, self.discord_user_id)


    def __clear_download_path(self):
        for file in self.download_path.rglob('*.*'):
            file.unlink()


    def __organize_environment(self):
        edit_script_qvs(
            script_path=self.script_path,
            company_name=self.company_name,
            narrative=self.narrative,
            month_analysis=self.month_analysis
        )

    def __init_browser(self):
        self.driver = init_browser(self.download_path)
        self.wait = WebDriverWait(self.driver, 60)


    def __control_qlik(self):
        prepare_page_to_process(self.driver, self.wait, self.agent_number)
        process_company(self.driver, self.wait)
        import ipdb; ipdb.set_trace()


    def run(self):
        if self.narrative == 'False':
            self.__discord_message(f'iniciei o processo para gerar o relatório em português da {self.company_name}')
        else:
            self.__discord_message(f'iniciei o processo para gerar o relatório em inglês da {self.company_name}')
        self.__clear_download_path()
        self.__organize_environment()
        self.__init_browser()
        self.__control_qlik()