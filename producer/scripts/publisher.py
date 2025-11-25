import pika
from loguru import logger


credentials = pika.PlainCredentials(
    username='admin',
    password='Suri123!'
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

channel.queue_declare(queue='discord_messages', durable=True)


channel.basic_publish(
    exchange='',
    routing_key='discord_messages',
    body='Ping!'
)

logger.info(" [x] Sent 'Hello World!'")


connection.close()