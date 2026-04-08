from extensions.google_cloud        import GoogleFirestore
from google.oauth2.service_account  import Credentials
from datetime                       import datetime, time
from zoneinfo                       import ZoneInfo
from loguru                         import logger
from googleapiclient.discovery      import build

import pika
import json
import uuid
import os




rabbitmq_username   = os.getenv('RABBITMQ_USERNAME')
rabbitmq_password   = os.getenv('RABBITMQ_PASSWORD')
drive_id_qvd        = os.getenv('DRIVE_ID_QVD')
host_rabbitmq       = os.getenv('RABBITMQ_HOST')
suridata_queue      = os.getenv('RABBITMQ_QUEUE')

fuso_brasilia = ZoneInfo('America/Sao_Paulo')



class DriveAPI():
    def __init__(self, parent_id):
        self.parent_id = parent_id


    def get_folders_drive_by_id(self, onlyFolder=True):
        logger.info(f'Iniciando busca no google drive usando o ID {self.parent_id}')
        
        try:
            creds = Credentials.from_service_account_file(
                './credentials/suridata-drive-access.json',
                scopes=['https://www.googleapis.com/auth/drive']
            )
        except Exception as error:
            logger.error(f'Erro ao se conectar na API do google: {error}')
            return []

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
    def __init__(self, message_data, job_id=None):
        self.job_id = job_id if job_id else str(uuid.uuid4())
        self.message_dict = message_data


    def __send_to_firestore(self):
        GoogleFirestore('jobs').set_job(self.job_id, data=self.message_dict)


    def __connection_rabbitmq(self):
        credentials = pika.PlainCredentials(
            username=rabbitmq_username,
            password=rabbitmq_password
        )

        logger.info('Abrindo conexão com RabbitMQ')
        self.connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                host=host_rabbitmq,
                port=5672,
                credentials=credentials,
                heartbeat=9000,
                blocked_connection_timeout=9000,
            )
        )

        self.channel = self.connection.channel()

    
    def __send_message_rabbitmq(self):
        logger.info('Postando nova mensagem')
        self.channel.queue_declare(queue=suridata_queue, durable=True)
        self.channel.basic_publish(
            exchange='',
            routing_key=suridata_queue,
            body=json.dumps({'job_id': self.job_id}).encode('utf-8')
        )

        logger.info('Fechando conexão com RabbitMQ')
        self.connection.close()


    def run(self):
        self.__send_to_firestore()
        self.__connection_rabbitmq()
        self.__send_message_rabbitmq()


def get_formated_time_now():
        return datetime.now(fuso_brasilia).strftime('%d/%m/%Y %H:%M:%S')
