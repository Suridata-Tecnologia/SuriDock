from start_process  import StartProcess
from functools      import partial
from common         import *



load_dotenv()
RABBITMQ_QUEUE      = os.getenv('RABBITMQ_QUEUE')


def return_message(ch, method, retry_count, headers, body):
    retry_count += 1
    if retry_count >= 5:
        logger.info(f"Descartando mensagem após {retry_count} tentativas")
        ch.basic_ack(method.delivery_tag)  # remove permanentemente
    else:
        # Atualiza headers com novo contador e reenfileira
        new_properties = pika.BasicProperties(
            headers={**headers, "x-retry-count": retry_count}
        )


        ch.basic_ack(method.delivery_tag)  # remove original
        ch.basic_publish(
            exchange='',
            routing_key=RABBITMQ_QUEUE,
            body=body,
            properties=new_properties
        ) # posta a cópia com retry_count+1


def get_retry_message(headers):
    retry_count = headers.get("x-retry-count", 0)
    return retry_count


def callback(ch, method, properties, body, agent_number):
    headers = properties.headers or {}
    retry_count = get_retry_message(headers)
    mensagem_json = json.loads(body.decode('utf-8'))
    success = StartProcess(agent_number, retry_count, mensagem_json).run()

    if success:
        ch.basic_ack(delivery_tag = method.delivery_tag)
    else:
        return_message(ch, method, retry_count, headers, body)


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