from extensions.suridata_api import SuridataApi
from dotenv                  import load_dotenv
from datetime                import timedelta 
from extensions.storage      import Storage
from extensions.adobe_api    import Convert
from extensions.trello       import Trello
from common                  import *
from selenium.webdriver.common.keys import Keys

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
        self.driver.get('https://portal.suridata.com.br/')

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


    def __save_debug(self, nome):
        try:
            debug_path = Path.cwd().joinpath('downloads', 'debug')
            debug_path.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            self.driver.save_screenshot(str(debug_path.joinpath(f'{nome}_{stamp}.png')))
            debug_path.joinpath(f'{nome}_{stamp}.html').write_text(self.driver.page_source, encoding='utf-8')
            logger.info(f'Debug salvo em {debug_path}')
        except Exception as e:
            logger.warning(f'Falha ao salvar debug: {e}')


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

        # Remove o conteúdo do relatório: assim o clique direito cai no fundo do canvas
        # (menu do relatório) e não em um gráfico (menu do componente).
        try:
            element_to_delete = self.driver.find_element(By.CSS_SELECTOR, 'ng2-report > ng2-canvas-container > div')
            self.driver.execute_script('arguments[0].remove();', element_to_delete)
        except Exception:
            logger.warning('Conteúdo do canvas não encontrado para remoção, seguindo mesmo assim')

        sleep(1)

        # O Looker Studio mudou: 'canvas-layout > div' agora tem altura 0, e quem recebe o
        # clique direito é o '.mainBlock'. Clicamos na lateral direita dele, fora da área do relatório.
        # O id do menu (mat-menu-panel-N) é dinâmico, então aceitamos qualquer botão do painel.
        menu_buttons_selector = '[id^="mat-menu-panel-"] button, .cdk-overlay-pane [role="menuitem"]'

        def visible_menu_buttons(driver):
            buttons = [b for b in driver.find_elements(By.CSS_SELECTOR, menu_buttons_selector) if b.is_displayed()]
            return buttons or False

        menu_buttons = None
        for tentativa in range(3):
            main_block = self.driver.find_element(By.CSS_SELECTOR, '.mainBlock')
            offset_x = 0 if tentativa == 1 else main_block.size['width'] // 2 - 40  # centro ou lateral direita
            ActionChains(self.driver).move_to_element_with_offset(main_block, offset_x, 0).context_click().perform()
            try:
                menu_buttons = WebDriverWait(self.driver, 10).until(visible_menu_buttons)
                if any('pdf' in b.text.lower() for b in menu_buttons):
                    break
                logger.warning(f'Menu sem opção de PDF: {[b.text.strip() for b in menu_buttons]}')
                ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                menu_buttons = None
                sleep(1)
            except TimeoutException:
                logger.warning(f'Menu de contexto não apareceu (tentativa {tentativa + 1}/3)')

        if not menu_buttons:
            self.__save_debug('menu_contexto')
            raise TimeoutException('Menu de contexto com opção de PDF não apareceu após o clique direito')

        next(b for b in menu_buttons if 'pdf' in b.text.lower()).click()

        # Dialog "Baixar o relatório (PDF)" (agora Angular Material, dentro do cdk-overlay)
        try:
            dialog = WebDriverWait(self.driver, 20).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, 'export-pdf-dialog'))
            )
            radio = next(r for r in dialog.find_elements(By.CSS_SELECTOR, 'mat-radio-button') if 'Selecionar' in r.text)
            radio.find_element(By.CSS_SELECTOR, 'input').click()

            # Marca todas as páginas do 5Pages (todas exceto a OnePage)
            WebDriverWait(self.driver, 10).until(
                lambda d: dialog.find_elements(By.CSS_SELECTOR, '[cdkdroplist] mat-checkbox')
            )
            paginas = []
            for checkbox in dialog.find_elements(By.CSS_SELECTOR, '[cdkdroplist] mat-checkbox'):
                nome = checkbox.get_attribute('textContent').strip()
                if not nome.startswith('5Pages'):
                    continue
                input_cb = checkbox.find_element(By.CSS_SELECTOR, 'input[type="checkbox"]')
                self.driver.execute_script('arguments[0].scrollIntoView({block: "center"});', input_cb)
                if not input_cb.is_selected():
                    self.driver.execute_script('arguments[0].click();', input_cb)
                paginas.append(nome)

            if not paginas:
                raise Exception('Nenhuma página "5Pages" encontrada no dialog de download')
            logger.info(f'Páginas selecionadas para o PDF: {paginas}')

            WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'export-pdf-dialog #download-button'))
            ).click()
        except Exception:
            self.__save_debug('dialog_pdf')
            raise

        # Aguarda o download terminar (arquivo .pdf sem .crdownload na pasta)
        self.__discord_message('baixando pdf...', 64)
        def pdf_baixado(_):
            pdfs = list(self.download_path.glob('*.pdf'))
            parciais = list(self.download_path.glob('*.crdownload'))
            return pdfs if pdfs and not parciais else False

        try:
            WebDriverWait(self.driver, 300, poll_frequency=2).until(pdf_baixado)
            sleep(2)
        except TimeoutException:
            self.__save_debug('download_pdf')
            logger.error('PDF não foi baixado em 5 minutos')
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
