from loguru                     import logger
from time                       import sleep
from common                     import *

import threading
import requests




class Trello():
    def __init__(self, list_source_name, list_target_name):
        self.suri_trello_api_key        = os.getenv('SURI_TRELLO_API_KEY')
        self.suri_trello_api_token      = os.getenv('SURI_TRELLO_API_TOKEN')
        self.suri_trello_board_id       = 'Vlpk9mpl'
        self.list_source_name           = list_source_name
        self.list_target_name           = list_target_name

        self.thread_trello = threading.Thread(target=self._trello_watcher, daemon=True)
        self.thread_trello.start()


    def trello_move_card(self, card_id: str, list_id: str):
        url = f'https://api.trello.com/1/cards/{card_id}'
        params = {
            'idList': list_id,
            'key': self.suri_trello_api_key,
            'token': self.suri_trello_api_token
        }
        resp = requests.put(url, params=params)
        if resp.status_code not in (200, 201):
            logger.error(f'Erro ao mover card {card_id}: {resp.text}')
        else:
            logger.info(f'Card {card_id} movido para lista {list_id}')


    def get_list_id_by_name(self, list_name: str):
        url = f'https://api.trello.com/1/boards/{self.suri_trello_board_id}/lists'
        params = {
            'key': self.suri_trello_api_key,
            'token': self.suri_trello_api_token
        }

        try:
            resp = requests.get(url, params=params)
            if resp.status_code != 200:
                logger.error(f'Erro ao consultar listas do board: {resp.text}')
                return None

            lists = resp.json()

            for lst in lists:
                if lst['name'].strip().lower() == list_name.strip().lower():
                    return lst['id']

            logger.error(f'Lista "{list_name}" não encontrada no board.')
            return None

        except Exception as e:
            logger.error(f'Erro ao buscar listas do board: {e}')
            return None


    def trello_list_cards(self, list_id: str):
        url = f"https://api.trello.com/1/lists/{list_id}/cards"
        params = {
            "key": self.suri_trello_api_key,
            "token": self.suri_trello_api_token
        }
        try:
            response = requests.get(url, params=params)
            if response.status_code != 200:
                logger.error(f"Erro ao buscar lista {list_id}: {response.text}")
                return []
            return response.json()
        except Exception as e:
            logger.error(f"Erro ao consultar Trello: {e}")
            return []
        

    def _trello_watcher(self):
        logger.info('Thread do Trello iniciada.')
        source_id = self.get_list_id_by_name(self.list_source_name)
        target_id = self.get_list_id_by_name(self.list_target_name)

        while True:
            try:
                if not source_id or not target_id:
                    sec = 5
                    logger.error(f'Não foi possível obter IDs das listas. Tentando novamente {sec}s...')
                    sleep(sec)
                    continue

                cards = self.trello_list_cards(source_id)

                for card in cards:
                    card_id = card['id']
                    card_name = card['name']

                    logger.info(f'Card encontrado para processamento: {card_name} ({card_id})')

                    # Mover o card para lista 'Operação: Processamento'
                    self.trello_move_card(card_id, target_id)

                    # Enviar mensagem ao RabbitMQ para iniciar processo
                    payload = {
                        'type_proccess': 'sentinel',
                        'created_at': get_formated_time_now(),
                        'company_name': None,
                        'discord_user_id': None,
                        'discord_message_id': None,
                        'trello_card_id': card_id,
                        'activity': None,
                        'month_analysis': None,
                        'audith': None,
                        'narrative': None,
                        'user_email': None,
                        'mail_list': None,
                        'discord_username': 'Bot - Sentinela',
                        'company_id': card_name.split(' - ')[0]
                    }
                    Producer(payload).run()

                # Esperar 5 segundos antes de consultar de novo
                sleep(5)

            except Exception as e:
                logger.error(f'Erro na thread Trello: {e}')
                sleep(5)