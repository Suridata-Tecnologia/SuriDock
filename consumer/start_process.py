from extensions.five_page       import FivePageFirst, FivePageSecond
from extensions.relatorio_ppt   import RelatorioPPT
from extensions.sentinel        import Sentinel
from extensions.storage         import Storage
from common                     import *

import traceback



class StartProcess():
    def __init__(self, agent_number, retry_count, job_id):
        self.agent_number       = agent_number
        self.retry_count        = retry_count
        self.job_id             = job_id
        
        self.qlik_use = Path('config/qlik_use.txt')

        self.apps = {
            'relatorioppt': {'class': RelatorioPPT, 'pretty_name': 'Relatório PPT'},
            'sentinel': {'class': Sentinel, 'pretty_name': 'Sentinela'},
            'storage':  {'class': Storage, 'pretty_name': 'Storage'},
            'fivepagefirst':  {'class': FivePageFirst, 'pretty_name': '5page'},
            'fivepagesecond':  {'class': FivePageSecond, 'pretty_name': '5page'}
        }


    def __need_run(self):
        self.firestore_data = GoogleFirestore('jobs').get_job(self.job_id)
        if self.firestore_data and self.firestore_data['status'] == 'cancelled':
            return False
        
        return True


    def __need_qlik(self):
        need_qlik_list = [
            'fivepagefirst',
            'relatorioppt',
            'sentinel',
            'storage'
        ]

        if self.firestore_data['type_proccess'] in need_qlik_list:
            return True
        
        return False
    

    def __create_necessary_files(self):
        folders = [
            Path(f'downloads/raw_files/agent{self.agent_number}/'),
            Path(f'downloads/ready_files/agent{self.agent_number}/')
        ]

        for folder in folders:
            if not folder.exists():
                folder.mkdir(parents=True)

        if not self.qlik_use.exists():
            if not self.qlik_use.parent.exists():
                self.qlik_use.parent.mkdir(parents=True)

            with open(self.qlik_use, 'w', encoding='utf-8') as f:
                f.write(f'agent1-stopped ## agent2-stopped ## agent3-stopped ## agent4-stopped')


    def __set_state_agent(self, state):
        with open(self.qlik_use, 'r', encoding='utf-8') as f:
            content = f.read()

        agents = content.split(' ## ')
        agents[self.agent_number-1] = f'agent{self.agent_number}-{state}'

        new_content = ''
        for agent in agents:
            new_content += f'{agent} ## '
        new_content = new_content[:-4]

        with open(self.qlik_use, 'w', encoding='utf-8') as f:
                f.write(new_content)


    def __close_qlik(self):
        with open(self.qlik_use, 'r', encoding='utf-8') as f:
            content = f.read()

        agents = content.split(' ## ')

        for agent in agents:
            if 'running' in agent:
                logger.info(f'{agent.split('-')[0]} usando o qlik, portando o agent{self.agent_number} o manterá aberto.')
                return False
            
        logger.info(f'Nenhum agente usando o qlik, agent{self.agent_number} fechando qlik e chrome...')
        close_process('chrome')
        close_process('qlik')

        return True


    def run(self):
        if not self.__need_run():
            return True

        GoogleFirestore('jobs').set_job(self.job_id, {'status': 'running'})
        
        self.__create_necessary_files()
        if self.__need_qlik():
            qlik_app = is_qlik_running()
            if not qlik_app:
                qlik_app = open_and_start_qlik(self.agent_number)

            self.__set_state_agent('running')

            try:
                operation_success = self.apps[self.firestore_data['type_proccess']]['class'](
                    self.agent_number,
                    self.retry_count,
                    self.job_id,
                    self.firestore_data,
                    self.apps[self.firestore_data['type_proccess']]['pretty_name']
                ).run()
            except Exception as error:
                operation_success = False
                timeline_error = traceback.format_exc()
                message_data = {
                    'discord_channel': 'sentinel' if self.firestore_data['type_proccess'] == 'sentinel' else 'bots',
                    'message_id': self.job_id,
                    'discord_username': self.firestore_data['discord_username'],
                    'company': self.firestore_data['company_name'],
                    'type_process': self.apps[self.firestore_data['type_proccess']]['pretty_name'],
                    'stage': 'Ocorreu um erro desconhecido',
                    'progress': 0,
                    'status': 'error',
                    'footer': self.firestore_data['created_at']
                }
                publish_message_discord(message_data)
                logger.error(f'Erro no processo {self.apps[self.firestore_data['type_proccess']]['pretty_name']}: {timeline_error}')

            self.__set_state_agent('stopped')
            self.__close_qlik()
        else:
            try:
                operation_success = self.apps[self.firestore_data['type_proccess']]['class'](
                    self.agent_number,
                    self.retry_count,
                    self.job_id,
                    self.firestore_data,
                    self.apps[self.firestore_data['type_proccess']]['pretty_name']
                ).run()
            except Exception as error:
                operation_success = False
                timeline_error = traceback.format_exc()
                message_data = {
                    'discord_channel': 'sentinel' if self.firestore_data['type_proccess'] == 'sentinel' else 'bots',
                    'message_id': self.job_id,
                    'discord_username': self.firestore_data['discord_username'],
                    'company': self.firestore_data['company_name'],
                    'type_process': self.apps[self.firestore_data['type_proccess']]['pretty_name'],
                    'stage': 'Ocorreu um erro desconhecido',
                    'progress': 0,
                    'status': 'error',
                    'footer': self.firestore_data['created_at']
                }
                publish_message_discord(message_data)
                logger.error(f'Erro no processo {self.apps[self.firestore_data['type_proccess']]['pretty_name']}: {timeline_error}')
            
        if operation_success:
            if not self.__need_run():
                return True
            
            GoogleFirestore('jobs').set_job(self.job_id, {'status': 'completed'})
            return True
            
        
        if not self.__need_run():
            return True
        
        GoogleFirestore('jobs').set_job(self.job_id, {'status': 'failed'})
        return False