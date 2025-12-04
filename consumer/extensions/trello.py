from dotenv import load_dotenv
from loguru import logger
from common import *

import requests
import os


load_dotenv()


class Trello():
    def __init__(self, card_id, list_target_name):
        self.suri_trello_api_key        = os.getenv('SURI_TRELLO_API_KEY')
        self.suri_trello_api_token      = os.getenv('SURI_TRELLO_API_TOKEN')
        self.suri_trello_board_id       = 'Vlpk9mpl'
        self.list_target_name           = list_target_name
        self.card_id                    = card_id


    def __trello_move_card(self, card_id: str, list_id: str):
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


    def __get_list_id_by_name(self, list_name: str):
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
        

    def __trello_control(self):
        target_id = self.__get_list_id_by_name(self.list_target_name)

        if not target_id:
            logger.error(f'Não foi possível obter o ID da lista.')

        # Mover o card para a lista alvo
        self.__trello_move_card(self.card_id, target_id)
        logger.info(f'Card {self.card_id} movido para a lista "{self.list_target_name}" com sucesso.')


    def run(self):
        self.__trello_control()