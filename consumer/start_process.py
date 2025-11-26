class StartProcess():
    def __init__(self, retry_count, body_message):
        self.retry_count = retry_count
        self.body_message = body_message

    def __transform_body(self):
        itens_list = self.body_message.split(' ## ')

        self.type_proccess = itens_list[0]
        

    def run(self):
        self.__transform_body()