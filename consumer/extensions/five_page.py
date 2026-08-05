from extensions.suridata_api import SuridataApi
from dotenv                  import load_dotenv
from datetime                import timedelta 
from extensions.storage      import Storage
from extensions.adobe_api    import Convert
from extensions.trello       import Trello
from common                  import *

import os


load_dotenv()
SURIPORTAL_USERNAME   = os.getenv('SURIPORTAL_USERNAME')
SURIPORTAL_PASSWORD   = os.getenv('SURIPORTAL_PASSWORD')



class FivePageFirst():
    def __init__(self, agent_number, retry_count, disc_message_id, message_json, pretty_name):
        self.disc_message_id    = disc_message_id
        self.mj                 = message_json
        self.agent_number       = agent_number
        self.retry_count        = retry_count
        self.pretty_name        = pretty_name

        if not self.mj['company_name']:
            self.mj['company_name'] = SuridataApi().get_company_by_id(self.mj['company_id'])['drive_folder']


    def __minutes_ahead(self, minutes: int):
        if self.mj['discord_user_id']:
            return datetime.now()
        
        return datetime.now() + timedelta(minutes=minutes)
    

    def __get_data(self):
        return {
            'pretty_name': self.pretty_name,
            'time_to_run': self.__minutes_ahead(15),
            'message_json': self.mj
        }


    def __run_storage(self):
        if self.mj['discord_user_id']:
            return True
        
        return Storage(self.agent_number, self.retry_count, self.disc_message_id, self.mj, self.pretty_name).run()


    def run(self):
        if self.__run_storage():
            self.mj['type_proccess'] = 'fivepagesecond'
            self.mj['status'] = 'queued'
            if is_local_mode():
                return FivePageSecond(
                    self.agent_number,
                    self.retry_count,
                    self.disc_message_id,
                    self.mj,
                    self.pretty_name
                ).run()

            GoogleFirestore('FivePage').set_job(
                job_id=self.disc_message_id,
                data=self.__get_data()
            )

            return True
        return False



class FivePageSecond():
    def __init__(self, agent_number, retry_count, disc_message_id, message_json, pretty_name):
        self.url, self.company_pretty_name = get_url_fivepage(message_json['company_name'])
        self.qvd_path           = Path('G:/Drives compartilhados/Ambiente de Produção/_QVD')
        self.download_path      = Path.cwd().joinpath(f'downloads/raw_files/agent{agent_number}/')
        self.disc_message_id    = disc_message_id
        self.mj                 = message_json
        self.pretty_name        = pretty_name


    def __move_card_trello(self, list_target_name):
        if self.mj['trello_card_id']:
            Trello(card_id=self.mj['trello_card_id'], list_target_name=list_target_name).run()


    def __discord_message(self, message, progress, status='running', discord_channel='bots'):
        message_data = {
            'discord_channel': discord_channel,
            'message_id': self.disc_message_id,
            'discord_username': self.mj['discord_username'],
            'company': self.mj['company_name'],
            'type_process': self.pretty_name,
            'english': 'Inglês :flag_us:' if self.mj['narrative'] else 'Português :flag_br:',
            'stage': message,
            'progress': progress,
            'status': status,
            'footer': self.mj['created_at']
        }
        publish_message_discord(message_data)


    def __init_browser(self):
        self.__discord_message('abrindo navegador', 0)
        self.driver = init_browser(self.download_path)
        self.wait = WebDriverWait(self.driver, 60)


    def __login(self):
        self.__discord_message('realizando login no portal da suridata', 16)
        self.driver.get('https://hml.portal.suridata.com.br/')

        self.driver.find_element(by='name', value='usuario').send_keys(SURIPORTAL_USERNAME)
        self.driver.find_element(by='name', value='senha').send_keys(SURIPORTAL_PASSWORD)

        # logger.info('Aguardando resolução do captcha...')
        # solution = bypass_captcha(
        #     'https://portal.suridata.com.br/',
        #     '6LcUkWUtAAAAAMG7zE4s8sCUhhInHvKkSUhFAi15'
        # )

        # self.driver.execute_script(f"document.getElementById('g-recaptcha-response').innerHTML = '{solution}'")
        self.driver.find_element(By.ID, 'button_login').click()


    def __navigate_into_pages(self):
        self.__discord_message('navegando entre as páginas do portal suridata', 32)
        self.driver.get(self.url)
        self.driver.maximize_window()


    def __download_pdf(self):
        # Fechando o novo spam caso apareça
        try:
            self.driver.find_element(By.XPATH, '/html/body/div[1]/div[4]/div/div/div/div[1]/button').click()
        except:
            pass

        self.driver.switch_to.frame(self.driver.find_element(by='css selector', value='body > div.content-wrapper > iframe'))

        # Espera até a página carregar
        self.__discord_message('aguardando a página carregar', 48)
        sleep(70)

        try:
            element_to_delete = self.driver.find_element(By.CSS_SELECTOR, '#body > div.lego-reporting-view.activity-view.no-licensed.new-resizer > div.pancake-view > ng2-reporting-plate > plate > div > div > div > div:nth-child(1) > div > div > div > div > div > canvas-pancake-adapter > canvas-layout > div > div > div.mainBlockHolder > div > div > div > ng2-report > ng2-canvas-container > div')
        except:
            element_to_delete = self.driver.find_element(By.CSS_SELECTOR, '#body > div > div.pancake-view > ng2-reporting-plate > plate > div > div > div > div:nth-child(1) > div > div > div > div > div > canvas-pancake-adapter > canvas-layout > div > div.mainBlockHolder > div > div > div > ng2-report > ng2-canvas-container > div')

        self.driver.execute_script('var element = arguments[0]; element.parentNode.removeChild(element);', element_to_delete)

        sleep(1)

        actionchains = ActionChains(self.driver)
        actionchains.context_click(self.driver.find_element(By.CSS_SELECTOR, '#body > div > div.pancake-view > ng2-reporting-plate > plate > div > div > div > div:nth-child(1) > div > div > div > div > div > canvas-pancake-adapter > canvas-layout > div')).perform()

        sleep(1)
        self.driver.find_element(by='css selector', value='#mat-menu-panel-0 > div > span > button').click()
        sleep(2)

        self.driver.find_element(By.XPATH, '/html/body/div[6]/md-dialog/md-dialog-content/div[1]/div[3]/div[1]/md-radio-group/md-radio-button[2]').click()

        self.driver.find_element(By.XPATH, '/html/body/div[6]/md-dialog/md-dialog-content/div[1]/div[3]/div[1]/div/ul/li[2]/div[1]').click()
        self.driver.find_element(By.XPATH, '/html/body/div[6]/md-dialog/md-dialog-content/div[1]/div[3]/div[1]/div/ul/li[3]/div[1]').click()
        self.driver.find_element(By.XPATH, '/html/body/div[6]/md-dialog/md-dialog-content/div[1]/div[3]/div[1]/div/ul/li[4]/div[1]').click()
        self.driver.find_element(By.XPATH, '/html/body/div[6]/md-dialog/md-dialog-content/div[1]/div[3]/div[1]/div/ul/li[5]/div[1]').click()
        self.driver.find_element(By.XPATH, '/html/body/div[6]/md-dialog/md-dialog-content/div[1]/div[3]/div[1]/div/ul/li[6]/div[1]').click()
        self.driver.find_element(By.XPATH, '/html/body/div[6]/md-dialog/md-dialog-content/div[1]/div[3]/div[1]/div/ul/li[7]/div[1]').click()
        self.driver.find_element(By.XPATH, '/html/body/div[6]/md-dialog/md-dialog-content/div[1]/div[3]/div[1]/div/ul/li[8]/div[1]').click()

        self.driver.find_element(by='css selector', value='body > div.md-dialog-container > md-dialog > md-dialog-actions > button.md-accent.md-raised.md-button.md-data-studio-theme.md-ink-ripple').click()

        sleep(1)
        retorno = self.driver.execute_script("return document.querySelector('body > md-toast > div > span')")

        while retorno:
            sleep(1)
            retorno = self.driver.execute_script("return document.querySelector('body > md-toast > div > span')")

        self.__discord_message('baixando pdf...', 64)
        sleep(30) # Aguarda o download ser concluído
        self.driver.close()


    def __move_to_drive(self):
        for file in self.download_path.rglob('*.pdf'):
            file_name = self.download_path.joinpath(f'{str(datetime.today().month).zfill(2)}.{datetime.today().year} - {self.company_pretty_name} - Análise de Gestão e Risco.pdf')
            destination_ppt = self.qvd_path.joinpath(self.mj['company_name'], 'base', f'{file_name.stem}.pptx')
            destination_pdf = self.qvd_path.joinpath(self.mj['company_name'], 'base', f'{file_name.stem}.pdf')

            file.rename(file_name)
            file_pdf = file_name

            sleep(2)
            self.__discord_message('convertendo pdf para ppt', 80)
            file_ppt = Convert(file_pdf).to_pptx()

            if file_ppt and file_ppt.exists():
                move_file(file_ppt, destination_ppt)

            move_file(file_pdf, destination_pdf)

            self.__discord_message('arquivo no drive :slight_smile:', 100, 'success')
            self.__move_card_trello('Qualidade: Produtos 6M')
            return True
        
        self.__move_card_trello('Saúde: Review')
        self.__discord_message('erro ao mover o arquivo para o drive', 0, 'error')
        return False


    def run(self):
        clear_folder(self.download_path)
        self.__init_browser()
        self.__login()
        self.__navigate_into_pages()
        self.__download_pdf()
        return self.__move_to_drive()
