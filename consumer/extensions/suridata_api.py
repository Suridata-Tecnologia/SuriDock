from dotenv import load_dotenv

import requests
import os


load_dotenv()
SURI_API_TOKEN   = os.getenv('SURI_API_TOKEN')


class SuridataApi:
    def __init__(self) -> None:
        self.token = SURI_API_TOKEN
        self.base_url = 'https://credentials-api-sar7gmwfia-ue.a.run.app'
        


    def get_company_by_id(self, id: int):
        headers = {'Authorization': self.token}
        response = requests.get(f'{self.base_url}/companies/{id}', headers=headers)
        data = response.json()['data']

        return data

    
    def get_companies_api(self):
        headers = {'Authorization': self.token}
        response = requests.get(f'{self.base_url}/companies', headers=headers)
        data = response.json()['data']

        return data