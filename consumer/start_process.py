from extensions.five_page       import FivePageFirst, FivePageSecond
from extensions.relatorio_ppt   import RelatorioPPT
from extensions.sentinel        import Sentinel
from extensions.storage         import Storage
from extensions.pipe            import Pipe
from common                     import *

import traceback



class StartProcess():
    def __init__(self, agent_number, retry_count, job_id=None, job_data=None):
        self.agent_number       = agent_number
        self.retry_count        = retry_count
        self.job_id             = job_id
        self.firestore_data     = job_data
        self.local_mode         = job_data is not None


        self.apps = {
            'relatorioppt': {'class': RelatorioPPT, 'pretty_name': 'Relatório PPT'},
            'sentinel': {'class': Sentinel, 'pretty_name': 'Sentinela'},
            'storage':  {'class': Storage, 'pretty_name': 'Storage'},
            'fivepagefirst':  {'class': FivePageFirst, 'pretty_name': '5page'},
            'fivepagesecond':  {'class': FivePageSecond, 'pretty_name': '5page'},
            'pipe':  {'class': Pipe, 'pretty_name': 'Pipe'}
        }


    def __need_run(self):
        if not self.local_mode:
            self.firestore_data = GoogleFirestore('jobs').get_job(self.job_id)
        if not self.firestore_data:
            return False
            
        if self.firestore_data['status'] == 'cancelled':
            return False
        
        return True


    def __need_qlik(self):
        need_qlik_list = [
            'fivepagefirst',
            'relatorioppt',
            'sentinel',
            'storage',
            'pipe'
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

        read_agent_states() # cria o config/qlik_use.txt se não existir


    def __set_state_agent(self, state):
        set_agent_state(self.agent_number, state)


    def __close_qlik(self):
        others = running_agents(exclude=self.agent_number)
        if others:
            logger.info(f'{others[0]} usando o qlik, portanto o agent{self.agent_number} o manterá aberto.')
            return False

        logger.info(f'Nenhum agente usando o qlik, agent{self.agent_number} fechando qlik e chrome...')
        close_process('chrome')
        close_process('qlik')

        return True


    def run(self):
        if not self.__need_run():
            return True

        if not self.local_mode:
            GoogleFirestore('jobs').set_job(self.job_id, {'status': 'running'})
        self.__create_necessary_files()
        if self.__need_qlik():
            # marca como "running" antes de mexer no qlik para outro agente não fechá-lo no meio do caminho
            self.__set_state_agent('running')

            try:
                if not ensure_qlik_ready(self.agent_number):
                    raise RuntimeError('O Qlik não ficou disponível (hub em localhost:4848 não respondeu)')

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
                    'discord_username': self.firestore_data['discord_username'] if 'discord_username' in list(self.firestore_data.keys()) else None,
                    'company': self.firestore_data['company_name'] if 'company_name' in list(self.firestore_data.keys()) else None,
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
            
            if not self.local_mode and self.firestore_data['type_proccess'] != 'fivepagefirst':
                GoogleFirestore('jobs').set_job(self.job_id, {'status': 'completed'})

            return True
            
        
        if not self.__need_run():
            return True
        
        if not self.local_mode:
            GoogleFirestore('jobs').set_job(self.job_id, {'status': 'failed'})
        return False
