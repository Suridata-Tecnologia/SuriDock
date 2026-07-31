from start_process              import StartProcess
from functools                  import partial
from common                     import *

load_dotenv()
RABBITMQ_QUEUE = os.getenv('RABBITMQ_QUEUE')


def return_message(ch, method, retry_count, disc_message_id, headers, body):
    retry_count += 1
    if retry_count >= 5:
        logger.info(f"Descartando mensagem após {retry_count} tentativas")
        ch.basic_ack(method.delivery_tag)  # remove permanentemente
    else:
        # Atualiza headers com novo contador e reenfileira
        new_properties = pika.BasicProperties(
            headers={**headers, 'x-retry-count': retry_count, 'disc_message_id': disc_message_id}
        )

        ch.basic_ack(method.delivery_tag)  # remove original
        ch.basic_publish(
            exchange='',
            routing_key=RABBITMQ_QUEUE,
            body=body,
            properties=new_properties
        ) # posta a cópia com retry_count+1


def get_retry_message(headers):
    retry_count = headers.get('x-retry-count', 0)
    return retry_count


def callback(ch, method, properties, body, agent_number):
    headers = properties.headers or {}
    retry_count = get_retry_message(headers)
    message_json = json.loads(body.decode('utf-8'))
    success = StartProcess(agent_number, retry_count, message_json['job_id']).run()

    if success:
        ch.basic_ack(delivery_tag = method.delivery_tag)
    else:
        return_message(ch, method, retry_count, message_json['job_id'], headers, body)


def start_consumer(agent):
    channel, connection = connection_rabbitmq()
    channel.queue_declare(queue=RABBITMQ_QUEUE, durable=True)
    channel.basic_qos(prefetch_count=1)

    callback_with_args = partial(callback, agent_number=agent)

    channel.basic_consume(
        queue=RABBITMQ_QUEUE,
        on_message_callback=callback_with_args
    )

    channel.start_consuming()


def start_local():
    processes = {
        '1': ('relatorioppt', 'Relatório PPT'),
        '2': ('storage', 'Storage'),
        '3': ('fivepagefirst', '5Page'),
        '4': ('sentinel', 'Sentinela'),
        '5': ('pipe', 'Pipe')
    }

    def required_input(label):
        while True:
            value = input(f'{label}: ').strip()
            if value:
                return value
            print('Este campo é obrigatório.')

    def boolean_input(label, default=False):
        default_label = 'S/n' if default else 's/N'

        while True:
            value = input(f'{label} ({default_label}): ').strip().lower()
            if not value:
                return default
            if value in ('s', 'sim'):
                return True
            if value in ('n', 'nao', 'não'):
                return False
            print('Digite "s" para sim ou "n" para não.')

    print('\nSelecione a tarefa que deseja executar:')
    for option, (_, pretty_name) in processes.items():
        print(f'  {option} - {pretty_name}')

    while True:
        option = input('Opção: ').strip()
        if option in processes:
            break
        print('Opção inválida.')

    type_process, pretty_name = processes[option]
    created_at = datetime.now(fuso_brasilia).strftime('%d/%m/%Y %H:%M:%S')
    job_data = {
        'status': 'queued',
        'type_proccess': type_process,
        'created_at': created_at,
        'company_name': None,
        'discord_user_id': None,
        'discord_message_id': None,
        'trello_card_id': None,
        'activity': None,
        'month_analysis': None,
        'audith': None,
        'narrative': False,
        'user_email': None,
        'mail_list': None,
        'discord_username': 'Execução local',
        'company_id': None
    }

    if type_process == 'pipe':
        job_data['operator'] = required_input('Nome da operadora')
        job_data['cards_id'] = []
    elif type_process == 'sentinel':
        job_data['company_name'] = required_input('Nome da pasta da empresa no _QVD')
    else:
        job_data['company_name'] = required_input('Nome da pasta da empresa no _QVD')

    if type_process == 'relatorioppt':
        job_data['narrative'] = boolean_input('Gerar relatório em inglês?')
        job_data['month_analysis'] = input('Mês de análise [não]: ').strip() or 'não'
        job_data['audith'] = boolean_input('Realizar auditoria?')
    elif type_process == 'fivepagefirst':
        job_data['dark_mode'] = boolean_input('Usar capa escura?')

    set_local_mode()
    logger.info(f'Iniciando {pretty_name} localmente')
    success = StartProcess(1, 0, job_data=job_data).run()

    if success:
        logger.success(f'{pretty_name} finalizado com sucesso')
    else:
        logger.error(f'{pretty_name} falhou')

    return success
