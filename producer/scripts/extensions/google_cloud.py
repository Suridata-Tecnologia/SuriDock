from google.cloud import firestore
from pathlib      import Path



class GoogleFirestore:
    def __init__(self):
        creds_path = Path.cwd().joinpath('credentials/suridock-database.json')
        self.db = firestore.Client.from_service_account_json(
            creds_path,
            project='suridata-prod',
            database='suri-se-suridock-jobs-db-prod'
        )


    def get_all_jobs(self):
        db = self.db.collection('jobs').stream()

        db_content = {}
        for data in db:
            db_content[data.id] = data.to_dict()

        return db_content
    

    # Método que cria ou atualiza jobs no Firestore
    def set_job(self, job_id: str, data: dict, merge: bool = True):
        doc_ref = self.db.collection('jobs').document(job_id)
        doc_ref.set(data, merge=merge)


    def delete_job(self, job_id: str) -> bool:
        doc_ref = self.db.collection('jobs').document(job_id)

        if not doc_ref.get().exists:
            return False

        doc_ref.delete()
        return True
