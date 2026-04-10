from dotenv import load_dotenv
from loguru import logger
from time   import sleep

import requests
import json
import os


load_dotenv()
ADOBE_CLIENT_ID     = os.getenv('ADOBE_CLIENT_ID')
ADOBE_CLIENT_SECRET = os.getenv('ADOBE_CLIENT_SECRET')



class Convert():
    def __init__(self, pdf_path):
        self.pdf_path = pdf_path


    def to_pptx(self):
        error = True
        trys = 10

        while error and trys > 0:
            url = 'https://pdf-services.adobe.io/token'

            files = {'file': open(self.pdf_path, 'rb')}

            payload = {
                'client_id': ADOBE_CLIENT_ID,
                'client_secret': ADOBE_CLIENT_SECRET
            }

            headers = {
                'Content-Type': 'application/x-www-form-urlencoded'
            }

            try:
                response = requests.request('POST', url, headers=headers, data=payload)
            except Exception as error:
                logger.error(f'Erro ao fazer post na API da adobe: {error}')
                return False
            
            try:
                if response.json()['message'].lower() == 'your ip is denylisted':
                    logger.error(f'IP do consumer banido: {response.json()}')
                    return False
            except:
                pass
            
            token = response.json()['access_token']

            ############################################################################################

            url = 'https://pdf-services.adobe.io/assets'

            payload = json.dumps({'mediaType': 'application/pdf'})
            headers = {
                'X-API-Key': ADOBE_CLIENT_ID,
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }

            response = requests.request('POST', url, headers=headers, data=payload)

            url = response.json()['uploadUri']
            asset_id = response.json()['assetID']

            headers = {
                'Content-Type': 'application/pdf'
            }

            response = requests.request('PUT', url, headers=headers, files=files)

            ############################################################################################

            url = 'https://pdf-services.adobe.io/operation/exportpdf'

            payload = json.dumps({
                'assetID': asset_id,
                'targetFormat': 'pptx',
                'ocrLang': 'pt-BR'
            })
            headers = {
                'Authorization': f'Bearer {token}',
                'x-api-key': ADOBE_CLIENT_ID,
                'Content-Type': 'application/json'
            }

            response = requests.request('POST', url, headers=headers, data=payload)

            url = response.headers['location']


            ############################################################################################

            headers = {
                'Authorization': f'Bearer {token}',
                'x-api-key': ADOBE_CLIENT_ID,
                'Content-Type': 'application/json'
            }

            response = requests.request('GET', url, headers=headers)

            while 'in progress' in response.text:
                logger.info('aguardando a API da adobe converter o PDF...')
                sleep(10)
                response = requests.request('GET', url, headers=headers)

            try:
                url = response.json()['asset']['downloadUri']
            except:
                logger.error(f'erro ao converter o arquivo {self.pdf_path.name} na API da adobe: {response.json()}')
                trys -= 1
                continue

            response = requests.request('GET', url)
            pptx_file = self.pdf_path.parent.joinpath(f'{self.pdf_path.stem}.pptx')
            with open(pptx_file, 'wb') as file_pptx:
                file_pptx.write(response.content)

            logger.success(f'arquivo {self.pdf_path.name} convertido com sucesso!')
            error = False
            files['file'].close()

        if error:
            return False
        
        return pptx_file

