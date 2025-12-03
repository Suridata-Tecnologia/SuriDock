from services.trello.trello     import Trello
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
        

    def _trello_watcher(self):
        logger.info('Thread do Trello iniciada.')

        trello_client = Trello()
        board = trello_client.get_board(self.suri_trello_board_id)
        while True:
            try:
                board_list = board.get_list_by_name(self.list_source_name)
                cards = board_list.get_cards()

                for card in cards:
                    card_id = card['id']
                    card_name = card['name']

                    logger.info(f'Card encontrado para processamento: {card_name} ({card_id})')

                    # Mover o card para lista 'Operação: Processamento'
                    self.trello_move_card(card_id, self.list_target_name)

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
                        'discord_name': 'Bot - Sentinela',
                        'company_id': card_name.split(' - ')[0]
                    }
                    Producer(payload).run()

                # Esperar 5 segundos antes de consultar de novo
                sleep(5)

            except Exception as e:
                logger.error(f'Erro na thread Trello: {e}')
                sleep(5)