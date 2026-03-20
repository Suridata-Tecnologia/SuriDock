from loguru import logger
from common import *



class FivePage():
    def __init__(self, discord_user_id, discord_message_id, companies, dark_mode):
        self.companies      = SplitCompanies(companies).run()
        self.message_id     = discord_message_id
        self.user_id        = discord_user_id
        self.dark_mode      = dark_mode


    def __aproved_to_queue(self):
        companies = CheckCompanies(self.companies).run()

        if companies:
            for company in companies:
                message_data = {
                    'status': 'queued',
                    'type_proccess': 'fivepage',
                    'created_at': get_formated_time_now(),
                    'company_name': company,
                    'discord_user_id': self.user_id,
                    'discord_message_id': self.message_id,
                    'trello_card_id': None,
                    'activity': None,
                    'month_analysis': None,
                    'audith': None,
                    'narrative': None,
                    'user_email': None,
                    'mail_list': None,
                    'discord_username': f'<@{self.user_id}>',
                    'company_id': None,
                    'dark_mode': self.dark_mode
                }
                Producer(message_data).run()
                
            if len(self.companies) == 1:
                self.answer_to_user = f'sua solicitação para gerar o 5page com capa {"escura" if self.dark_mode else "clara"} da empresa {self.companies[0]} foi adicionada na fila'
            else:
                self.answer_to_user = f'as empresas a seguir foram adicionadas na fila: {", ".join(self.companies)}'
        else:
            if len(self.companies) == 1:
                self.answer_to_user = f'não encontrei a empresa {self.companies[0]}\nPor favor verifique se você digitou o nome da pasta em _QVD corretamente'
            else:
                self.answer_to_user = f'as empresas a seguir não foram encontradas na pasta _QVD: {", ".join(self.companies)}'


    def run(self):
        self.__aproved_to_queue()
        return self.answer_to_user