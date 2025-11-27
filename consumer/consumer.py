from start_process  import StartProcess
from dotenv         import load_dotenv
from common         import *

import pika
import os



load_dotenv()
RABBITMQ_HOST       = os.getenv('RABBITMQ_HOST')
RABBITMQ_USERNAME   = os.getenv('RABBITMQ_USERNAME')
RABBITMQ_PASSWORD   = os.getenv('RABBITMQ_PASSWORD')
RABBITMQ_MESSAGES   = os.getenv('RABBITMQ_MESSAGES')
RABBITMQ_QUEUE      = os.getenv('RABBITMQ_QUEUE')


def connection_rabbitmq():
    credentials = pika.PlainCredentials(
        username=RABBITMQ_USERNAME,
        password=RABBITMQ_PASSWORD
    )

    connection = pika.BlockingConnection(
        pika.ConnectionParameters(
            host=RABBITMQ_HOST,
            port=5672,
            credentials=credentials,
            heartbeat=600,
            blocked_connection_timeout=600,
        )
    )

    channel = connection.channel()
    return channel


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


def callback(ch, method, properties, body):
    headers = properties.headers or {}
    retry_count = get_retry_message(headers)
    success = StartProcess(retry_count, body.decode()).run()

    if success:
        ch.basic_ack(delivery_tag = method.delivery_tag)
    else:
        return_message(ch, method, retry_count, headers, body)


def start_consumer():
    channel = connection_rabbitmq()
    channel.queue_declare(queue=RABBITMQ_QUEUE, durable=True)
    channel.basic_consume(
        queue=RABBITMQ_QUEUE,
        on_message_callback=callback
    )

    logger.info('Pronto para receber mensagens!')
    channel.start_consuming()