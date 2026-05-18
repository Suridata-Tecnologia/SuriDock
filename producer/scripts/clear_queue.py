from extensions.google_cloud    import GoogleFirestore
from loguru                     import logger



class ClearQueue():
    def __init__(self):
        self.database = GoogleFirestore('jobs').get_all_jobs()
        self.status_to_delete = ['failed', 'cancelled', 'completed']
        self.jobs_to_delete = []


    def __filter_jobs(self, need_filter=True):
        for data in self.database:
            if need_filter:
                if self.database[data]['status'] in self.status_to_delete:
                    self.jobs_to_delete.append(data)
            else:
                self.jobs_to_delete.append(data)


    def __delete_jobs(self):
        if self.jobs_to_delete:
            delete_count = GoogleFirestore('jobs').delete_jobs_batch(self.jobs_to_delete)
        else:
            delete_count = 0

        logger.info(f'{delete_count} jobs excluídos')


    def run(self):
        self.__filter_jobs()
        self.__delete_jobs()
