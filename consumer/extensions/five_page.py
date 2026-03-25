from extensions.google_cloud import GoogleStorage
from extensions.suridata_api import SuridataApi
from dotenv                  import load_dotenv
from extensions.trello       import Trello
from common                  import *

import os



load_dotenv()
MACHINE_NAME = os.getenv('MACHINE_NAME')


class FivePage():
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
            'english': 'Inglês :flag_us:' if self.mj['narrative'] else 'Português :flag_br:',
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
        self.__discord_message('editando script do qlik', 15)
        self.__move_card_trello('Operação: Atualizando no Portal (Storage)') # coluna de quando o processo inicia
        self.gestao_pos = has_gestao_pos(self.mj['company_name'])
        edit_script_qvs(
            script_path=self.script_path,
            company_name=self.mj['company_name'],
            activity='Portal',
            language='Portugues',
            month_analysis='não'
        )

    def __init_browser(self):
        self.__discord_message('abrindo navegador', 30)
        self.driver = init_browser(self.download_path)
        self.wait = WebDriverWait(self.driver, 60)


    def __control_qlik(self):
        navigate_to_process(self.driver, self.wait, self.agent_number)
        self.__discord_message('aguardando qlik processar a operadora', 45)
        if not process_company(self.driver):
            return False
        
        return True
    

    def __move_to_storage(self):
        self.__discord_message('subindo os arquivos para o storage', 60)
        bases_path = {
            'Base 10Maiores'     : self.qvd_path.joinpath('_Base Storage', 'Base 10Maiores'),
            'Base Auditoria'     : self.qvd_path.joinpath('_Base Storage', 'Base Auditoria'),
            'Base Beneficiarios' : self.qvd_path.joinpath('_Base Storage', 'Base Beneficiarios'),
            'Base Highlights'    : self.qvd_path.joinpath('_Base Storage', 'Base Highlights'),
            'Base Resumo'        : self.qvd_path.joinpath('_Base Storage', 'Base Resumo'),
            'Base Utilização'    : self.qvd_path.joinpath('_Base Storage', 'Base Utilização')
        }

        for base in bases_path:
            for file in bases_path[base].glob(f'*{self.mj["company_name"]}*'):
                try:
                    cloud_storage = GoogleStorage(f'suri-storage')
                    cloud_storage.upload_file(file, file.name, 'text/csv', f'Extração Produção/{base}')
                except Exception as error:
                    logger.error(f'erro ao subir os dados pra base: {error}')
                    return False
                
                logger.success(f'Arquivo movido para o storage: {file.name}')
                sleep(1)
                file.unlink()
                logger.info(f'Arquivo removido: {file}')
                break

        return True


    def __start_suripoint(self):
        self.__discord_message('Aguardando os arquivos aparecer no storage', 75)
        sleep(30)

        logger.info(f'Iniciando start no suripoint...')
        self.__discord_message('Clicando em "Play" no suripoint', 90)
        try:
            response = requests.post('https://suri-automate-gcs-sar7gmwfia-rj.a.run.app/start', timeout=3600)
        except requests.exceptions.ReadTimeout:
            response = None

        if not response:
            logger.error(f'Suripoint não respondeu, e provavelmente deu ruim')
            return False
        if response.status_code == 200:
            logger.success(f'Suripoint rodou com sucesso!')
            return True
        elif response.status_code == 500:
            logger.warning(f'Suripoint retornou 500 mas provavelmente funcionou: {response.text}')
            return True
        else:
            logger.error(f'Erro ao rodar o Suripoint: {response.status_code} {response.text}')
            return False
    

    def __move_card_trello(self, list_target_name):
        if self.mj['trello_card_id']:
            Trello(card_id=self.mj['trello_card_id'], list_target_name=list_target_name).run()


    def __manager_qlik_and_move_to_storage(self):
        if self.__control_qlik():
            if self.__move_to_storage():
                if self.__start_suripoint():
                    self.__discord_message('Suripoint processou corretamente', 100, 'success')
                    self.__move_card_trello('Saúde: Validação dados Portal 👀👀👀') # coluna de quando o processo da certo
                    return True
                else:
                    self.__discord_message('Arquivos subiu para o storage mas o suripoint falhou', 0, 'error')
                    self.__move_card_trello('Operação: Ajustes e Correções Portal') # coluna de quando o processo falha
                    return False
            else:
                self.__discord_message('erro ao subir os arquivos para o storage', 0, 'error')
                self.__move_card_trello('Operação: Ajustes e Correções Portal') # coluna de quando o processo falha
                return False
        else:
            self.__discord_message('erro no qlik', 0, 'error')
            self.__move_card_trello('Operação: Ajustes e Correções Portal') # coluna de quando o processo falha
            return False


    def run(self):
        self.__clear_download_path()
        self.__organize_environment()
        self.__init_browser()
        return self.__manager_qlik_and_move_to_storage()
