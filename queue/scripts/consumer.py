from loguru import logger
import pika


credentials = pika.PlainCredentials(
    username='???',
    password='???'
)

connection = pika.BlockingConnection(
    pika.ConnectionParameters(
        host='localhost',
        port=5672,
        credentials=credentials,
        heartbeat=600,
        blocked_connection_timeout=600,
    )
)


channel = connection.channel()

channel.queue_declare(queue='teste', durable=True)

def callback(ch, method, properties, body):
    ch.basic_ack(delivery_tag = method.delivery_tag)
    logger.info(f" [x] Received {body}")

channel.basic_consume(
    queue='teste',
    on_message_callback=callback
)

channel.start_consuming()