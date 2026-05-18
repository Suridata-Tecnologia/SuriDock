from dotenv                         import load_dotenv
from extensions.trello              import Trello
from selenium.webdriver.common.keys import Keys
from common                         import *

import os



load_dotenv()
MACHINE_NAME = os.getenv('MACHINE_NAME')


class Pipe():
    def __init__(self, agent_number, retry_count, job_id, message_json, pretty_name):
        self.qvd_path           = Path('G:/Drives compartilhados/Ambiente de Produção/_QVD')
        self.download_path      = Path.cwd().joinpath(f'downloads/raw_files/agent{agent_number}/')
        self.ready_path         = Path.cwd().joinpath(f'downloads/ready_files/agent{agent_number}/')
        self.script_path        = get_path_script_qvs(self.qvd_path, agent_number)

        self.mj                 = message_json
        self.agent_number       = agent_number
        self.retry_count        = retry_count


    def __init_browser(self):
        self.driver = init_browser(self.download_path)
        self.wait = WebDriverWait(self.driver, 60)
        self.actions = ActionChains(self.driver)


    def __control_qlik(self):
        navigate_to_process(self.driver, self.wait, self.agent_number, app_name=f'pipe{self.agent_number}')
        self.wait.until(EC.presence_of_element_located((By.XPATH, '/html/body/div[4]/div[3]/div/qmfe-embed-react/qmfe-root/div/div[1]/div[2]/div[1]/div/div[1]/div/div/ul/div/div[2]/li/button/div[2]/div/p'))).click()


    def __run_operator(self):
        operator_obj = self.wait.until(EC.presence_of_element_located((By.XPATH, '/html/body/div[4]/div[3]/div/qmfe-embed-react/qmfe-root/div/div[1]/div[2]/div[1]/div/div[3]/main/div/div[2]/qmfe-embed-react/qmfe-root/scripteditor-code-area/div/div/div/div[6]/div[1]/div/div/div/div[5]/div[27]/pre/span/span[4]')))
        operator_name = f"let vG_Operadora = '{self.mj['operator']}';"
        operator_obj.click()
        self.actions.send_keys(Keys.END)\
            .key_down(Keys.SHIFT)\
            .send_keys(Keys.HOME)\
            .key_up(Keys.SHIFT)\
            .send_keys(Keys.DELETE)\
            .send_keys(operator_name)\
            .perform()

        type_process_name = ["let vG_Processo = 'Sinistro';", "let vG_Processo = 'Premio';", "let vG_Processo = 'Sinistralidade';"]
        for type_process in type_process_name:
            self.driver.find_element(By.XPATH, '/html/body/div[4]/div[3]/div/qmfe-embed-react/qmfe-root/div/div[1]/div[2]/div[1]/div/div[3]/main/div/div[2]/qmfe-embed-react/qmfe-root/scripteditor-code-area/div/div/div/div[6]/div[1]/div/div/div/div[5]/div[29]/pre/span/span[4]').click()
            self.actions.send_keys(Keys.END)\
                .key_down(Keys.SHIFT)\
                .send_keys(Keys.HOME)\
                .key_up(Keys.SHIFT)\
                .send_keys(Keys.DELETE)\
                .send_keys(type_process)\
                .perform()

            self.driver.find_element(By.XPATH, '/html/body/div[4]/div[1]/header/div/div[3]/button').click() # salva a página
            logger.info(f'rodando pipe para a operadora {self.mj["operator"]}')
            success = process_company(self.driver)
            if not success:
                break

        return success


    def __move_card_trello(self):
        for card_id in self.mj['cards_id']:
            Trello(card_id=card_id, list_target_name='Operação: Aguardando Processamento').run()


    def run(self):
        self.__init_browser()
        self.__control_qlik()
        success = self.__run_operator()
        if success:
            self.__move_card_trello()
            logger.success(f'{self.mj["operator"]} rodou com sucesso!')
        else:
            logger.error(f'{self.mj["operator"]} erro no qlik')

        return success
