from common import *



class ManagerQueue():
    def get_queued_and_running(self):
        db = GoogleFirestore().get_all_jobs()

        data_list = []
        status_accepted = ['queued', 'running']
        for data in db:
            if db[data]['status'] in status_accepted:
                data_list.append([data, db[data]])

        if data_list:
            return data_list
        
        return None


    def cancel_job(self, job_id):
        GoogleFirestore().set_job(job_id, data={'status': 'cancelled'})
