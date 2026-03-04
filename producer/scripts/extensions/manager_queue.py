from common import *



class ManagerQueue():
    def __init__(self):
        self.db = GoogleFirestore().get_all_jobs()


    def __get_queued_and_running(self):
        for data in self.db:
            import ipdb; ipdb.set_trace()
            

    def run(self):
        self.__get_queued_and_running()
        return