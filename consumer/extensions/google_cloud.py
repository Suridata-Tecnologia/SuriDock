from google.cloud import storage, firestore
from pathlib      import Path


class GoogleStorage:
    def __init__(self, bucket):
        creds_path = Path.cwd().joinpath('credentials/suribase.json')
        self.client = storage.Client.from_service_account_json(creds_path)
        self.bucket = self.client.get_bucket(bucket)


    def upload_file(self, filepath, new_filename, content_type, *prefix) -> None:
        blob_name = Path(*prefix, new_filename).as_posix()
        blob = self.bucket.blob(blob_name)
        blob.upload_from_filename(filepath, content_type)

    
    def list_files_cloud_storage(self):
        self.path = 'suri-storage/validação_qlik'
        blobs = list(self.bucket.list_blobs(prefix=self.path))
        return blobs[1:]



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
    

    def get_job(self, job_id: str) -> dict | None:
        doc_ref = self.db.collection('jobs').document(job_id)
        doc = doc_ref.get()

        if not doc.exists:
            return None

        return doc.to_dict()
    

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
