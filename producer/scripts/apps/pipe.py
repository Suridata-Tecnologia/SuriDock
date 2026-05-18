from common                     import Producer, get_formated_time_now
from extensions.suridata_api    import SuridataApi
from extensions.trello          import Trello
from loguru                     import logger



class Pipe():
    def __init__(self):
        self.trello = Trello('Pipe: Processamento')
        self.source_id = self.trello.get_list_id_by_name()
        self.operators_to_run = {}


    def __read_trello(self):
        cards = self.trello.trello_list_cards(self.source_id)
        
        for card in cards:
            card_id = card['id']
            card_name = card['name']
            company = SuridataApi().get_company_by_id(card_name.split(' - ')[0])

            if company['operator']['name'] in list(self.operators_to_run.keys()):
                self.operators_to_run[company['operator']['name']].append(card_id)
            else:
                self.operators_to_run[company['operator']['name']] = [card_id]


    def __send_to_queue(self):
        for operator in self.operators_to_run:
            message_data = {
                'status': 'queued',
                'type_proccess': 'pipe',
                'created_at': get_formated_time_now(),
                'operator': operator,
                'cards_id': self.operators_to_run[operator]
            }
            Producer(message_data).run()
            logger.info(f'Operadora "{operator}" adicionada na fila')


    def run(self):
        self.__read_trello()
        self.__send_to_queue()