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
        self.gestao_pos = has_gestao_pos(self.company_name)
        edit_script_qvs(
            script_path=self.script_path,
            company_name=self.company_name,
            narrative=self.narrative,
            month_analysis=self.month_analysis,
            gestao_pos=self.gestao_pos
        )

    def __init_browser(self):
        self.driver = init_browser(self.download_path)
        self.wait = WebDriverWait(self.driver, 60)


    def __control_qlik(self):
        navigate_to_process(self.driver, self.wait, self.agent_number)
        process_company(self.driver)
        return navigate_to_export(self.driver, self.wait, self.narrative, self.gestao_pos)
    

    def __answer_user(self, begin):
        if begin:
            if self.retry_count == 0:
                if self.narrative == 'False':
                    self.__discord_message(f'iniciei o processo para gerar o relatório em português da {self.company_name}')
                else:
                    self.__discord_message(f'iniciei o processo para gerar o relatório em inglês da {self.company_name}')
            else:
                if self.narrative == 'False':
                    self.__discord_message(f'iniciei o processo para gerar o relatório em português da {self.company_name} pela {self.retry_count+1}° vez')
                else:
                    self.__discord_message(f'iniciei o processo para gerar o relatório em inglês da {self.company_name} pela {self.retry_count+1}° vez')
        else:
            if self.retry_count == 0:
                if self.narrative == 'False':
                    self.__discord_message(f'relatorio em português da {self.company_name} gerado e salvo no drive :white_check_mark:')
                elif self.narrative == 'True':
                    self.__discord_message(f'relatorio em inglês da {self.company_name} gerado e salvo no drive :white_check_mark:')
            else:
                if self.narrative == 'False':
                    self.__discord_message(f'relatorio em português da {self.company_name} gerado e salvo no drive depois de {self.retry_count+1} tentativas :white_check_mark:')
                elif self.narrative == 'True':
                    self.__discord_message(f'relatorio em inglês da {self.company_name} gerado e salvo no drive depois de {self.retry_count+1} tentativas :white_check_mark:')

    def __manager_qlik_and_move_to_drive(self):
        download_success = self.__control_qlik()
        if download_success:
            wait_until_download_finish(self.download_path, self.driver)
            company_pretty_name, audit_date, suridata_product = get_pretty_name(self.company_name)
            is_audith = need_audith(self.audith, company_pretty_name, audit_date, suridata_product)
            if move_to_drive(self.qvd_path, self.company_name, is_audith, self.download_path, self.narrative, company_pretty_name):
                self.__answer_user(False)
                return True
            else:
                self.__discord_message(f'houve um erro com o suripoint e não foi possível gerar o arquivo da {self.company_name} ❌')
        else:
            self.__discord_message(f'houve um erro com o qlik e não foi possível gerar o arquivo da {self.company_name} ❌')
        
        return False


    def run(self):
        self.__answer_user(True)
        self.__clear_download_path()
        self.__organize_environment()
        self.__init_browser()
        return self.__manager_qlik_and_move_to_drive()
