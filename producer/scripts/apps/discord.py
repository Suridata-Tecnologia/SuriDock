from extensions.relatorio_ppt       import RelatorioPPT
from discord                        import app_commands
from discord.ext                    import commands
from datetime                       import datetime
from zoneinfo                       import ZoneInfo
from extensions.trello              import Trello
from loguru                         import logger
from time                           import sleep
from math                           import ceil

import threading
import requests
import asyncio
import discord
import pika
import json
import os



fuso_brasilia = ZoneInfo("America/Sao_Paulo")


class DiscordBot:
    def __init__(self):
        # Carrega variáveis de ambiente
        self.discord_id_channel_bots    = int(os.getenv('DISCORD_ID_CHANNEL_BOTS'))
        self.rabbitmq_username          = os.getenv('RABBITMQ_USERNAME')
        self.rabbitmq_password          = os.getenv('RABBITMQ_PASSWORD')
        self.rabbitmq_messages          = os.getenv('RABBITMQ_MESSAGES')
        self.discord_webhook            = os.getenv('DISCORD_WEBHOOK')
        self.discord_token              = os.getenv('DISCORD_TOKEN')
        self.rabbitmq_host              = os.getenv('RABBITMQ_HOST')
        self.time_to_delete             = 180
        self.active_embeds              = {}

        # Discord
        intents = discord.Intents.default()
        intents.messages = True
        self.client = commands.Bot(command_prefix=None, intents=intents)
        self.tree = self.client.tree
        self.STATUS_EMOJIS = {
            "pending": "⏳",
            "running": "🔄",
            "success": "✅",
            "error": "❌"
        }

        self.STATUS_COLORS = {
            "pending": discord.Color.yellow(),
            "running": discord.Color.blue(),
            "success": discord.Color.green(),
            "error": discord.Color.red(),
        }

        # Evento assíncrono para aguardar o Discord iniciar antes de enviar mensagens
        self.discord_ready_event = asyncio.Event()

        # Registro de event handlers
        self._register_handlers()
        self._register_commands()

        self.trello = Trello(
            list_source_name='Operação: Aguardando Processamento',
            list_target_name='Operação: Processamento'
        )


    # ----------------------------------------------------------
    # Handlers de eventos do Discord
    # ----------------------------------------------------------
    def _register_handlers(self):
        @self.client.event
        async def on_ready():
            logger.info(f"Bot conectado como {self.client.user}")

            # Sincronizar slash commands com o Discord
            try:
                synced = await self.tree.sync()
                logger.info(f"Slash commands sincronizados: {[cmd.name for cmd in synced]}")
            except Exception as e:
                logger.error(f"Erro ao sincronizar slash commands: {e}")

            self.discord_ready_event.set()


    # ----------------------------------------------------------
    # Slash commands do Discord
    # ----------------------------------------------------------
    def _register_commands(self):
        @self.tree.command(name="ping", description="Retorna uma resposta de teste.")
        async def ping(interaction: discord.Interaction):
            await interaction.response.defer()
            message = await interaction.followup.send(f'{interaction.user.mention} Processando sua solicitação...', ephemeral=False)
            await interaction.followup.edit_message(message_id=message.id, content=f'{interaction.user.mention} Pong!')
            await asyncio.sleep(self.time_to_delete)
            await interaction.delete_original_response()


        @self.tree.command(name="relatorioppt", description="Gera o relatório pelo qlik")
        @app_commands.describe(empresa='Digite o nome da pasta em _QVD para criar o relatório', ingles='Escolha True se quiser o relatório em inglês', mes_analise='Escolha o período para analisar')
        async def relatorioppt(interaction: discord.Interaction, empresa: str, ingles: bool = False, mes_analise: str = 'não', auditoria: bool = False):
            await interaction.response.defer()
            message = await interaction.followup.send(f'{interaction.user.mention} Processando sua solicitação...', ephemeral=False)
            
            if ingles:
                answer_english = RelatorioPPT(interaction.user.id, message.id, empresa, True, mes_analise, auditoria).run()
                answer_portuguese = RelatorioPPT(interaction.user.id, message.id, empresa, False, mes_analise, auditoria).run()

                if not 'já esta na fila' in answer_english.lower() and not 'já esta na fila' in answer_portuguese.lower():
                    answer_to_user = f'suas solicitações para gerar os relatórios em inglês e português da empresa {empresa.upper()} foram adicionadas na fila'
                elif not 'já esta na fila' in answer_english.lower():
                    answer_to_user = answer_english
                elif not 'já esta na fila' in answer_portuguese.lower():
                    answer_to_user = answer_portuguese
                else:
                    answer_to_user = f'os relatórios em inglês e português da empresa {empresa.upper()} já estão na fila ✋'
            else:
                answer_to_user = RelatorioPPT(interaction.user.id, message.id, empresa, False, mes_analise, auditoria).run()

            await interaction.followup.edit_message(message_id=message.id, content=f'{interaction.user.mention} {answer_to_user}')
            await asyncio.sleep(self.time_to_delete)
            await interaction.delete_original_response()


    # ----------------------------------------------------------
    # Cria uma barra de progresso no discord
    # ----------------------------------------------------------
    def build_progress_bar(self, percent: int, size: int = 20) -> str:
        percent = max(0, min(100, percent))
        filled = int((percent / 100) * size)
        empty = size - filled
        return "🟩" * filled + "⬜" * empty + f" {percent}%"


    # ----------------------------------------------------------
    # Recebe um dict com dados do processo e cria ou atualiza um embed associado ao message_id.
    # ----------------------------------------------------------
    async def send_or_update_embed(self, message_json: dict):
        await self.discord_ready_event.wait()

        channel = self.client.get_channel(self.discord_id_channel_bots)
        if not channel:
            logger.error('Canal do Discord não encontrado.')
            return

        status = message_json.get('status', 'running')
        emoji = self.STATUS_EMOJIS.get(status, '🔄')
        color = self.STATUS_COLORS.get(status, discord.Color.blue())

        progress = int(message_json.get('progress', 0))
        progress_bar = self.build_progress_bar(progress)

        # Construir embed
        embed = discord.Embed(
            title=f'{emoji} Status - {message_json['type_process']} {emoji}',
            description=f'**{message_json.get('stage', 'Executando...')}**',
            color=color
        )

        embed.add_field(name='Solicitante', value=message_json.get('discord_username', '-'), inline=True)
        embed.add_field(name='Empresa', value=message_json.get('company', '-'), inline=True)

        if '-' != message_json.get('english', '-'):
            embed.add_field(name='Idioma', value=message_json.get('english', '-'), inline=False)

        embed.add_field(
            name='Progresso',
            value=progress_bar,
            inline=False
        )

        if status != 'success':
            embed.set_footer(text=f'Pedido feito ás {message_json.get('footer', '-')}')
        else:
            # Calcula o tempo
            created_at = datetime.strptime(message_json['footer'], '%d/%m/%Y %H:%M:%S')
            time_now = datetime.strptime(datetime.now(fuso_brasilia).strftime('%d/%m/%Y %H:%M:%S'), '%d/%m/%Y %H:%M:%S')
            minutes = ceil((time_now - created_at).seconds / 60)
            embed.set_footer(text=f'Concluído em {minutes} minutos')


        # Caso já exista mensagem deste processo
        if message_json['message_id'] in self.active_embeds:
            info = self.active_embeds[message_json['message_id']]
            try:
                msg = await channel.fetch_message(info['message_id'])
                await msg.edit(embed=embed)
                logger.info(f'Embed do processo {message_json['message_id']} atualizado.')
                return
            except Exception as e:
                logger.error(f'Erro ao editar embed existente: {e}')

        # Caso seja a primeira mensagem do processo
        message = await channel.send(embed=embed)
        self.active_embeds[message_json['message_id']] = {
            'message_id': message.id,
            'channel_id': channel.id
        }

        logger.info(f'Novo embed criado para processo {message_json['message_id']}.')


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

                channel.queue_declare(queue=self.rabbitmq_messages, durable=True)
                channel.basic_qos(prefetch_count=1)
                logger.info(f"Conectado. Consumindo fila '{self.rabbitmq_messages}'.")

                for method, properties, body in channel.consume(
                    self.rabbitmq_messages, inactivity_timeout=1
                ):
                    if body is None:
                        continue

                    message_json = json.loads(body.decode('utf-8'))

                    # Enviar menssagem ao Discord
                    asyncio.run_coroutine_threadsafe(
                        self.send_or_update_embed(message_json),
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
