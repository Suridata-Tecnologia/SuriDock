from start_process              import StartProcess
from common                     import *

import traceback

load_dotenv()
RABBITMQ_QUEUE  = os.getenv('RABBITMQ_QUEUE')
MAX_RETRIES     = 5
POLL_INTERVAL   = 5 # segundos entre consultas à fila quando ela está vazia


# Por que não usamos basic_consume + ack no final do job:
# o job roda por dezenas de minutos e, enquanto isso, o pika não manda heartbeat
# para o RabbitMQ. O broker derruba a conexão, o ack final falha (StreamLostError)
# e a mensagem volta para a fila, fazendo outro agente reprocessar o mesmo job.
# Por isso o agente pega UMA mensagem (basic_get), confirma na hora, fecha a conexão
# e só então processa. O retry é feito republicando a mensagem em caso de falha,
# e o estado do job continua no Firestore.


def requeue_message(retry_count, job_id, headers, body):
    retry_count += 1
    if retry_count >= MAX_RETRIES:
        logger.info(f'Descartando job {job_id} após {retry_count} tentativas')
        return

    properties = pika.BasicProperties(
        headers={**headers, 'x-retry-count': retry_count, 'disc_message_id': job_id}
    )

    for attempt in range(1, 4):
        try:
            channel, connection = connection_rabbitmq()
            try:
                channel.queue_declare(queue=RABBITMQ_QUEUE, durable=True)
                channel.basic_publish(
                    exchange='',
                    routing_key=RABBITMQ_QUEUE,
                    body=body,
                    properties=properties
                )
            finally:
                connection.close()

            logger.info(f'Job {job_id} recolocado na fila (tentativa {retry_count + 1}/{MAX_RETRIES})')
            return
        except Exception as error:
            logger.error(f'Erro ao recolocar o job {job_id} na fila ({attempt}/3): {error}')
            sleep(10)

    logger.error(f'Não foi possível recolocar o job {job_id} na fila, ele foi perdido')


def get_next_message():
    # espera a próxima mensagem, confirma (ack) e fecha a conexão antes de processar
    channel, connection = connection_rabbitmq()
    try:
        channel.queue_declare(queue=RABBITMQ_QUEUE, durable=True)

        while True:
            if restart_pending():
                connection.sleep(POLL_INTERVAL) # restart agendado: não pega jobs novos
                continue

            method, properties, body = channel.basic_get(queue=RABBITMQ_QUEUE, auto_ack=False)
            if method is None:
                connection.sleep(POLL_INTERVAL) # connection.sleep mantém os heartbeats em dia
                continue

            channel.basic_ack(delivery_tag=method.delivery_tag)
            return properties, body
    finally:
        try:
            connection.close()
        except Exception:
            pass


def process_message(properties, body, agent_number):
    headers = properties.headers or {}
    retry_count = headers.get('x-retry-count', 0)

    try:
        job_id = json.loads(body.decode('utf-8'))['job_id']
    except Exception:
        logger.error(f'Mensagem inválida descartada: {body!r}')
        return

    # marca o agente como ocupado já aqui, para o outro agente não fechar o qlik
    # enquanto este ainda está abrindo/preparando o processo
    set_agent_state(agent_number, 'running')
    try:
        success = StartProcess(agent_number, retry_count, job_id).run()
    except Exception:
        logger.error(f'Erro ao processar o job {job_id}: {traceback.format_exc()}')
        success = False
    finally:
        set_agent_state(agent_number, 'stopped')

    if not success:
        requeue_message(retry_count, job_id, headers, body)


def start_consumer(agent):
    while True:
        properties, body = get_next_message()
        process_message(properties, body, agent)


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
