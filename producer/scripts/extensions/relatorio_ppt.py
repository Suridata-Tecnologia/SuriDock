from loguru import logger
from common import *



class RelatorioPPT():
    def __init__(self, discord_user_id, discord_message_id, companies, english, month_analysis, user_audith):
        self.companies      = SplitCompanies(companies).run()
        self.message_id     = discord_message_id
        self.user_id        = discord_user_id
        self.month_analysis = month_analysis
        self.user_audith    = user_audith
        self.english        = english


    def __aproved_to_queue(self):
        companies = CheckCompanies(self.companies).run()

        if companies:
            for company in companies:
                message_data = {
                    'type_proccess': 'relatorioppt',
                    'created_at': get_formated_time_now(),
                    'company_name': company,
                    'discord_user_id': self.user_id,
                    'discord_message_id': self.message_id,
                    'trello_card_id': None,
                    'activity': None,
                    'month_analysis': self.month_analysis,
                    'audith': self.user_audith,
                    'narrative': self.english,
                    'user_email': None,
                    'mail_list': None
                }
                Producer(message_data).run()
                
            if len(self.companies) == 1:
                if self.english:
                    self.answer_to_user = f'sua solicitação para gerar o relatório em inglês da empresa {self.companies[0]} foi adicionada na fila'
                else:
                    self.answer_to_user = f'sua solicitação para gerar o relatório em português da empresa {self.companies[0]} foi adicionada na fila'
            else:
                self.answer_to_user = f'as empresas a seguir foram adicionadas na fila \n{self.companies}'
        else:
            if len(self.companies) == 1:
                self.answer_to_user = f'não encontrei a empresa {self.companies[0]}\nPor favor verifique se você digitou o nome da pasta em _QVD corretamente'
            else:
                self.answer_to_user = f'as empresas a seguir não foram encontradas na pasta _QVD\n{self.companies}'


    def run(self):
        self.__aproved_to_queue()
        return self.answer_to_user