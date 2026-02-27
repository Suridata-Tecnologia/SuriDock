from google.cloud import storage
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
