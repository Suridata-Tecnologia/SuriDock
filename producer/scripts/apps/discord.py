from loguru import logger
from time   import sleep

import threading
import requests
import asyncio
import discord
import pika
import os



# salva os logs
logger.add('logs/script.log')


class DiscordBot:
    def __init__(self):
        # Carrega variáveis de ambiente
        self.discord_id_channel_bots    = int(os.getenv("DISCORD_ID_CHANNEL_BOTS"))
        self.discord_token              = os.getenv("DISCORD_TOKEN")
        self.discord_webhook            = os.getenv("DISCORD_WEBHOOK")
        self.rabbitmq_host              = os.getenv("RABBITMQ_HOST")
        self.rabbitmq_queue             = os.getenv("RABBITMQ_QUEUE")
        self.rabbitmq_username          = os.getenv("RABBITMQ_USERNAME")
        self.rabbitmq_password          = os.getenv("RABBITMQ_PASSWORD")

        # Discord
        intents = discord.Intents.default()
        intents.messages = True
        self.client = discord.Client(intents=intents)

        # Evento assíncrono para aguardar o Discord iniciar antes de enviar mensagens
        self.discord_ready_event = asyncio.Event()

        # Registro de event handlers
        self._register_handlers()


    # ----------------------------------------------------------
    # Handlers de eventos do Discord
    # ----------------------------------------------------------
    def _register_handlers(self):
        @self.client.event
        async def on_ready():
            logger.info(f"Bot conectado como {self.client.user}")
            self.discord_ready_event.set()


    # ----------------------------------------------------------
    # Enviar mensagem para canal
    # ----------------------------------------------------------
    async def send_to_channel(self, message: str):
        await self.discord_ready_event.wait()
        channel = self.client.get_channel(self.discord_id_channel_bots)

        if channel is None:
            logger.error(f"Canal {self.discord_id_channel_bots} não encontrado.")
            return

        await channel.send(message)


    # ----------------------------------------------------------
    # Enviar mensagem para webhook
    # ----------------------------------------------------------
    def send_to_webhook(self, message, webhook=None):
        if not webhook:
            webhook = self.discord_webhook

            bot_name = 'SuriDock'
                
            data = {
                'username': bot_name,
                'content': message
            }

            result = requests.post(webhook, json=data, headers={'Content-Type': 'application/json'})
            if not (200 <= result.status_code < 300):
                logger.error(f'Erro ao enviar a mensagem: {result.status_code}, Resultado: {result.text}')
                logger.error(f'Menssagem que seria enviada ao discord: {message}')


    # ----------------------------------------------------------
    # Consumidor RabbitMQ rodando em thread
    # ----------------------------------------------------------
    def _rabbitmq_consumer(self, loop: asyncio.AbstractEventLoop):
        while True:
            try:
                logger.info("Conectando ao RabbitMQ...")

                credentials = pika.PlainCredentials(
                    username=self.rabbitmq_username,
                    password=self.rabbitmq_password
                )

                connection = pika.BlockingConnection(
                    pika.ConnectionParameters(host=self.rabbitmq_host, credentials=credentials)
                )
                channel = connection.channel()

                channel.queue_declare(queue=self.rabbitmq_queue, durable=True)
                logger.info(f"Conectado. Consumindo fila '{self.rabbitmq_queue}'.")

                for method, properties, body in channel.consume(
                    self.rabbitmq_queue, inactivity_timeout=1
                ):
                    if body is None:
                        continue

                    message = body.decode()
                    logger.info(f"Recebido do RabbitMQ: {message}")

                    # Enviar menssagem ao Discord
                    asyncio.run_coroutine_threadsafe(
                        self.send_to_channel(message),
                        loop
                    )

                    channel.basic_ack(method.delivery_tag)

            except Exception as error:
                time_to_sleep = 60
                error_message = f'Erro ao se conectar no RabbitMQ: {error}. Tentando novamente em {time_to_sleep}s...'
                logger.error(error_message)
                self.send_to_webhook(message=error_message)
                sleep(time_to_sleep)

    # ----------------------------------------------------------
    # Método principal de execução
    # ----------------------------------------------------------
    async def _start(self):
        loop = asyncio.get_running_loop()

        # Inicia thread do RabbitMQ
        thread = threading.Thread(
            target=self._rabbitmq_consumer,
            args=(loop,),
            daemon=True
        )
        thread.start()

        # Inicia o bot
        await self.client.start(self.discord_token)

    # ----------------------------------------------------------
    # Método público
    # ----------------------------------------------------------
    def run(self):
        asyncio.run(self._start())
