class StartProcess():
    def __init__(self, retry_count, body_message):
        self.retry_count = retry_count
        self.body_message = body_message

    def __transform_body(self):
        itens_list = self.body_message.split(' ## ')

        self.type_proccess      = itens_list[0],
        self.created_at         = itens_list[1],
        self.company_name       = itens_list[2],
        self.discord_user_id    = itens_list[3],
        self.discord_message_id = itens_list[4],
        self.trello_card_id     = itens_list[5],
        self.activity           = itens_list[6],
        self.monthAnalysis      = itens_list[7],
        self.audith             = itens_list[8],
        self.narrative          = itens_list[9],
        self.user_email         = itens_list[10],
        self.mail_list          = itens_list[11]


    def run(self):
        self.__transform_body()
        import ipdb; ipdb.set_trace()