from google.oauth2.service_account  import Credentials
from datetime                       import datetime
from loguru                         import logger
from googleapiclient.discovery      import build

import pika
import os




rabbitmq_username   = os.getenv("RABBITMQ_USERNAME")
rabbitmq_password   = os.getenv("RABBITMQ_PASSWORD")
drive_id_qvd        = os.getenv("DRIVE_ID_QVD")
host_rabbitmq       = os.getenv('RABBITMQ_HOST')
suridata_queue      = os.getenv('RABBITMQ_QUEUE')



class DriveAPI():
    def __init__(self, parent_id):
        self.parent_id = parent_id


    def get_folders_drive_by_id(self, onlyFolder=True):
        logger.info(f'Iniciando busca no google drive usando o ID {self.parent_id}')
        creds = Credentials.from_service_account_file(
            './apps/credentials/suridata-drive-access.json',
            scopes=['https://www.googleapis.com/auth/drive']
        )

        drive = build("drive", "v3", credentials=creds)

        folders = []
        page_token = None

        while True:
            response = drive.files().list(
                q=f"'{self.parent_id}' in parents and mimeType='application/vnd.google-apps.folder'",
                fields='nextPageToken, files(id, name)',
                includeItemsFromAllDrives=True,
                supportsAllDrives=True,
                pageToken=page_token,
                pageSize=1000  # limite máximo permitido
            ).execute()

            folders.extend(response.get("files", []))

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        logger.info(f'{len(folders)} pastas encontradas')

        if onlyFolder:
            new_folders = []
            for folder in folders:
                new_folders.append(folder['name'])

            return new_folders

        return folders
    

class CheckCompanies():
    def __init__(self, companies):
        self.companies = companies


    def __remove_if_no_exists(self):
        folders = DriveAPI(parent_id=drive_id_qvd).get_folders_drive_by_id()
        
        new_companies_list = []
        for company in self.companies:
            if company.upper() in folders:
                new_companies_list.append(company)

        self.companies = new_companies_list


    def run(self):
        self.__remove_if_no_exists()
        logger.info(f'{len(self.companies)} empresa(s) encontrada(s) em _QVD')
        return self.companies



class SplitCompanies():
    def __init__(self, companies):
        self.companies = companies.upper()


    def __split_companies(self):
        self.companies = self.companies.split(',')
        self.companies = [company.strip() for company in self.companies]
        logger.info(f'{len(self.companies)} empresa(s) recebida(s) pelo usuário')
        return self.companies


    def run(self):
        self.__split_companies()
        return self.companies
    


class Producer():
    def __init__(
            self,
            type_proccess,
            created_at,
            company_name,
            discord_user_id=None,
            discord_message_id=None,
            trello_card_id=None,
            activity=None,
            monthAnalysis=None,
            audith=None,
            app_name=None,
            narrative=None,
            user_email=None,
            mail_list=None
        ):
        self.discord_message_id = str(discord_message_id)
        self.discord_user_id    = str(discord_user_id)
        self.trello_card_id     = str(trello_card_id)
        self.type_proccess      = str(type_proccess)
        self.monthAnalysis      = str(monthAnalysis)
        self.company_name       = str(company_name)
        self.created_at         = str(created_at)
        self.user_email         = str(user_email)
        self.narrative          = str(narrative)
        self.mail_list          = str(mail_list)
        self.activity           = str(activity)
        self.app_name           = str(app_name)
        self.audith             = str(audith)


    def __connection_rabbitmq(self):
        credentials = pika.PlainCredentials(
            username=rabbitmq_username,
            password=rabbitmq_password
        )

        connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                host=host_rabbitmq,
                port=5672,
                credentials=credentials,
                heartbeat=600,
                blocked_connection_timeout=600,
            )
        )

        logger.info('Abrindo conexão com o RabbitMQ')
        channel = connection.channel()
        channel.queue_declare(queue=suridata_queue, durable=True)
        logger.info('Postando novo conteúdo na fila')
        channel.basic_publish(
            exchange='',
            routing_key=suridata_queue,
            body=f'{self.type_proccess} ## {self.created_at} ## {self.company_name} ## {self.discord_user_id} ## {self.discord_message_id} ## {self.trello_card_id} ## {self.activity} ## {self.monthAnalysis} ## {self.audith} ## {self.app_name} ## {self.narrative} ## {self.user_email} ## {self.mail_list}'
        )
        connection.close()
        logger.info('Fechando conexão com o RabbitMQ')


    def run(self):
        self.__connection_rabbitmq()


def get_formated_time_now():
        return datetime.now().strftime('%d/%m/%Y %H:%M:%S')
