from google.cloud import firestore
from pathlib      import Path



class GoogleFirestore:
    def __init__(self, table: str):
        self.table = table
        creds_path = Path.cwd().joinpath('credentials/suridock-database.json')
        self.db = firestore.Client.from_service_account_json(
            creds_path,
            project='suridata-prod',
            database='suri-se-suridock-jobs-db-prod'
        )


    def get_all_jobs(self):
        db = self.db.collection(self.table).stream()

        db_content = {}
        for data in db:
            db_content[data.id] = data.to_dict()

        return db_content
    

    # Método que cria ou atualiza as tables no Firestore
    def set_job(self, job_id: str, data: dict, merge: bool = True):
        doc_ref = self.db.collection(self.table).document(job_id)
        doc_ref.set(data, merge=merge)


    def delete_job(self, job_id: str) -> bool:
        doc_ref = self.db.collection(self.table).document(job_id)

        if not doc_ref.get().exists:
            return False

        doc_ref.delete()
        return True
    

    def delete_jobs_batch(self, job_ids: list[str]) -> int:
        batch = self.db.batch()
        count = 0

        for job_id in job_ids:
            doc_ref = self.db.collection(self.table).document(job_id)
            batch.delete(doc_ref)
            count += 1

            # Firestore limita em 500 operações por batch
            if count % 500 == 0:
                batch.commit()
                batch = self.db.batch()

        # Commit final (restante)
        if count % 500 != 0:
            batch.commit()

        return count
