from extensions.suridata_api import SuridataApi
from dotenv                  import load_dotenv
from datetime                import timedelta 
from extensions.storage      import Storage
from common                  import *

import os


load_dotenv()
MACHINE_NAME = os.getenv('MACHINE_NAME')



class FivePageFirst():
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


    def __minutes_ahead(self, minutes: int):
        return datetime.now() + timedelta(minutes=minutes)
    

    def __get_data(self):
        return {
            'pretty_name': self.pretty_name,
            'time_to_run': self.__minutes_ahead(15),
            'message_json': self.mj
        }


    def __run_storage(self):
        return Storage(self.agent_number, self.retry_count, self.disc_message_id, self.mj, self.pretty_name).run()


    def run(self):
        if self.__run_storage():
            self.mj['type_proccess'] = 'fivepagesecond'
            self.mj['status'] = 'queued'
            GoogleFirestore('FivePage').set_job(
                job_id=self.disc_message_id,
                data=self.__get_data()
            )

            return True
        return False



class FivePageSecond():
    def __init__(self, agent_number, retry_count, disc_message_id, message_json, pretty_name):
        pass


    def run():
        pass