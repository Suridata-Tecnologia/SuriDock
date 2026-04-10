from extensions.google_cloud    import GoogleFirestore
from datetime                   import datetime
from loguru                     import logger
from common                     import Producer



class FivePage():
    def __init__(self):
        self.db = GoogleFirestore('FivePage').get_all_jobs()
        self.jobs_to_run = []


    def __verify_date(self):
        for job in self.db:
            future = datetime.fromtimestamp(self.db[job]['time_to_run'].timestamp())
            if datetime.now() > future:
                self.jobs_to_run.append(job)


    def __set_data(self):
        for job in self.jobs_to_run:
            logger.info(f'Colocando {job} em jobs')
            Producer(self.db[job]['message_json'], job_id=job).run()
            GoogleFirestore('FivePage').delete_job(job_id=job)


    def run(self):
        self.__verify_date()
        self.__set_data()
