from dotenv import load_dotenv
from common import *

import uuid
import os


unique_id = str(uuid.uuid4())



load_dotenv()
MACHINE_NAME = os.getenv('MACHINE_NAME')


class RelatorioPPT():
    def __init__(self, agent_number, retry_count, message_json):
        self.qvd_path           = Path('G:/Drives compartilhados/Ambiente de Produção/_QVD')
        self.download_path      = Path.cwd().joinpath(f'downloads/raw_files/agent{agent_number}/')
        self.ready_path         = Path.cwd().joinpath(f'downloads/ready_files/agent{agent_number}/')
        self.script_path        = get_path_script_qvs(self.qvd_path, agent_number)

        self.agent_number       = agent_number
        self.retry_count        = retry_count
        self.mj                 = message_json


    def __discord_message(self, message):
        publish_message_discord(message, self.mj['discord_user_id'])


    def __clear_download_path(self):
        for file in self.download_path.rglob('*.*'):
            file.unlink()


    def __organize_environment(self):
        self.gestao_pos = has_gestao_pos(self.mj['company_name'])
        edit_script_qvs(
            script_path=self.script_path,
            company_name=self.mj['company_name'],
            narrative=self.mj['narrative'],
            month_analysis=self.mj['month_analysis'],
            gestao_pos=self.gestao_pos
        )

    def __init_browser(self):
        self.driver = init_browser(self.download_path)
        self.wait = WebDriverWait(self.driver, 60)


    def __control_qlik(self):
        navigate_to_process(self.driver, self.wait, self.agent_number)
        process_company(self.driver)
        return navigate_to_export(self.driver, self.wait, self.mj['narrative'], self.gestao_pos)
    

    def __answer_user(self, begin):
        if begin:
            if self.retry_count == 0:
                if self.mj['narrative']:
                    self.__discord_message(f'iniciei o processo para gerar o relatório em inglês da {self.mj["company_name"]}')
                else:
                    self.__discord_message(f'iniciei o processo para gerar o relatório em português da {self.mj["company_name"]}')
            else:
                if self.mj['narrative']:
                    self.__discord_message(f'iniciei o processo para gerar o relatório em inglês da {self.mj["company_name"]} pela {self.retry_count+1}° vez')
                else:
                    self.__discord_message(f'iniciei o processo para gerar o relatório em português da {self.mj["company_name"]} pela {self.retry_count+1}° vez')
        else:
            if self.retry_count == 0:
                if self.mj['narrative']:
                    self.__discord_message(f'relatorio em inglês da {self.mj["company_name"]} gerado e salvo no drive :white_check_mark:')
                else:
                    self.__discord_message(f'relatorio em português da {self.mj["company_name"]} gerado e salvo no drive :white_check_mark:')
            else:
                if self.mj['narrative']:
                    self.__discord_message(f'relatorio em inglês da {self.mj["company_name"]} gerado e salvo no drive depois de {self.retry_count+1} tentativas :white_check_mark:')
                else:
                    self.__discord_message(f'relatorio em português da {self.mj["company_name"]} gerado e salvo no drive depois de {self.retry_count+1} tentativas :white_check_mark:')


    def __manager_qlik_and_move_to_drive(self):
        download_success = self.__control_qlik()
        if download_success:
            wait_until_download_finish(self.download_path, self.driver)
            company_pretty_name, audit_date, suridata_product = get_pretty_name(self.mj['company_name'])
            is_audith = need_audith(self.mj['audith'], company_pretty_name, audit_date, suridata_product)
            if move_to_drive(self.qvd_path, self.mj['company_name'], is_audith, self.download_path, self.mj['narrative'], company_pretty_name):
                self.__answer_user(False)
                return True
            else:
                self.__discord_message(f'houve um erro com o suripoint e não foi possível gerar o arquivo da {self.mj["company_name"]} ❌')
        else:
            self.__discord_message(f'houve um erro com o qlik e não foi possível gerar o arquivo da {self.mj["company_name"]} ❌')
        
        return False


    def run(self):
        self.__answer_user(True)
        self.__clear_download_path()
        self.__organize_environment()
        self.__init_browser()
        return self.__manager_qlik_and_move_to_drive()
