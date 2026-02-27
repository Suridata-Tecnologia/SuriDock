from google.cloud import firestore
from pathlib      import Path



class GoogleFirestore:
    def __init__(self):
        creds_path = Path.cwd().joinpath('credentials/suridock-database.json')
        self.db = firestore.Client.from_service_account_json(creds_path)


    def run(self):
        docs = self.db.collection('jobs').stream()

        for doc in docs:
            print(doc.id, doc.to_dict())