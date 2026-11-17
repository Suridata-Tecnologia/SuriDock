"""Bot do Discord: cards de status vindos do consumer, /ver_fila, /remover_fila e webhook.

O cliente do Discord não conecta: os canais e mensagens são dublês, e as threads
do Trello não são iniciadas.
"""
import asyncio
from datetime import datetime, timedelta

import pytest

from apps import discord as discord_app


class FakeMessage:
    def __init__(self, message_id, embed):
        self.id = message_id
        self.embed = embed
        self.edits = []

    async def edit(self, embed):
        self.edits.append(embed)
        self.embed = embed


class FakeChannel:
    def __init__(self, channel_id):
        self.id = channel_id
        self.messages = {}
        self.next_id = 1000

    async def send(self, embed):
        self.next_id += 1
        message = FakeMessage(self.next_id, embed)
        self.messages[message.id] = message
        return message

    async def fetch_message(self, message_id):
        return self.messages[message_id]


@pytest.fixture
def bot(monkeypatch):
    trellos = []

    class FakeTrello:
        def __init__(self, list_source_name, list_target_name=None):
            trellos.append((list_source_name, list_target_name))

    monkeypatch.setattr(discord_app, 'Trello', FakeTrello)
    instance = discord_app.DiscordBot()
    instance.trellos = trellos
    instance.channels = {111: FakeChannel(111), 222: FakeChannel(222)}
    monkeypatch.setattr(instance.client, 'get_channel', lambda channel_id: instance.channels.get(channel_id))
    return instance


def send(bot, message):
    async def go():
        bot.discord_ready_event.set()
        await bot.send_or_update_embed(message)
    asyncio.run(go())


def status_message(**overrides):
    data = {
        'discord_channel': 'bots',
        'message_id': 'job-1',
        'discord_username': 'Trello - Card 1406',
        'company': 'BIOAGRI_AMIL',
        'type_process': '5page',
        'stage': 'aguardando qlik processar a operadora',
        'progress': 45,
        'status': 'running',
        'footer': '16/11/2026 10:21:06',
    }
    data.update(overrides)
    return data


def fields(embed):
    return {field.name: field.value for field in embed.fields}


# --- inicialização --------------------------------------------------------------

def test_bot_observa_as_quatro_listas_do_trello(bot):
    assert bot.trellos == [
        ('Operação: Aguardando Processamento', 'Operação: Processamento'),
        ('Qualidade: Processar PPT', 'Qualidade: Processando PPT'),
        ('Operação: Atualizar no Portal (Storage) 🎉', 'Operação: Atualizando no Portal (Storage)'),
        ('Qualidade: Upload 6M', 'Qualidade: Processando 6M'),
    ]


def test_bot_le_os_canais_das_variaveis_de_ambiente(bot):
    assert bot.discord_id_channel_bots == 111
    assert bot.discord_id_channel_sentinel == 222


# --- barra de progresso ---------------------------------------------------------

@pytest.mark.parametrize('percent, filled', [(0, 0), (45, 9), (50, 10), (100, 20), (150, 20), (-10, 0)])
def test_barra_de_progresso(bot, percent, filled):
    bar = bot.build_progress_bar(percent)

    assert bar.count('🟩') == filled
    assert bar.count('⬜') == 20 - filled
    assert bar.endswith(f' {max(0, min(100, percent))}%')


# --- cards de status --------------------------------------------------------------

def test_primeira_mensagem_cria_o_card_no_canal_bots(bot):
    send(bot, status_message())

    [message] = bot.channels[111].messages.values()
    embed = message.embed
    assert embed.title == '🔄 Status - 5page 🔄'
    assert embed.description == '**aguardando qlik processar a operadora**'
    assert fields(embed)['Solicitante'] == 'Trello - Card 1406'
    assert fields(embed)['Empresa'] == 'BIOAGRI_AMIL'
    assert fields(embed)['Progresso'].endswith(' 45%')
    assert embed.footer.text == 'Pedido feito ás 16/11/2026 10:21:06'
    assert bot.active_embeds['job-1'] == {'message_id': message.id, 'channel_id': 111}


def test_mensagens_seguintes_editam_o_mesmo_card(bot):
    send(bot, status_message(progress=15))
    send(bot, status_message(progress=45))

    [message] = bot.channels[111].messages.values()
    assert len(message.edits) == 1
    assert fields(message.embed)['Progresso'].endswith(' 45%')


def test_sentinela_vai_para_o_outro_canal(bot):
    send(bot, status_message(discord_channel='sentinel'))

    assert bot.channels[111].messages == {}
    assert len(bot.channels[222].messages) == 1


def test_erro_mostra_o_motivo_enviado_pelo_consumer(bot):
    send(bot, status_message(status='error', progress=0, stage='Erro: IndexError: list index out of range'))

    [message] = bot.channels[111].messages.values()
    assert message.embed.title == '❌ Status - 5page ❌'
    assert message.embed.description == '**Erro: IndexError: list index out of range**'


def test_idioma_so_aparece_quando_enviado(bot):
    send(bot, status_message())
    send(bot, status_message(message_id='job-2', english='Português :flag_br:'))

    first, second = bot.channels[111].messages.values()
    assert 'Idioma' not in fields(first.embed)
    assert fields(second.embed)['Idioma'] == 'Português :flag_br:'


@pytest.mark.parametrize('elapsed, expected', [
    (timedelta(minutes=5), 'Concluído em 5 minutos'),
    (timedelta(minutes=95), 'Concluído em 1 hora e 35 minutos'),
    (timedelta(hours=2, minutes=10), 'Concluído em 2 horas e 10 minutos'),
])
def test_sucesso_mostra_o_tempo_total(bot, elapsed, expected):
    # o código arredonda para cima (minuto começado conta inteiro): 4min30s vira 5 minutos
    created = datetime.now(discord_app.fuso_brasilia) - elapsed + timedelta(seconds=30)

    send(bot, status_message(status='success', progress=100, footer=created.strftime('%d/%m/%Y %H:%M:%S')))

    [message] = bot.channels[111].messages.values()
    assert message.embed.footer.text == expected


def test_canal_inexistente_nao_quebra(bot):
    bot.channels = {}

    send(bot, status_message())

    assert bot.active_embeds == {}


def test_card_apagado_no_discord_e_recriado(bot):
    send(bot, status_message())
    bot.channels[111].messages.clear()

    send(bot, status_message(progress=60))

    assert len(bot.channels[111].messages) == 1


# --- /ver_fila --------------------------------------------------------------------

@pytest.fixture
def queue(monkeypatch):
    state = {'jobs': None, 'cancelled': []}

    class FakeManagerQueue:
        def get_queued_and_running(self):
            return state['jobs']

        def cancel_job(self, job_id):
            state['cancelled'].append(job_id)

    monkeypatch.setattr(discord_app, 'ManagerQueue', FakeManagerQueue)
    return state


def job(company, type_proccess='sentinel', status='queued', narrative=None):
    return {'company_name': company, 'type_proccess': type_proccess, 'status': status, 'narrative': narrative}


def test_ver_fila_vazia(bot, queue):
    assert bot._set_embed_from_queue() is None


def test_ver_fila_monta_empresa_tipo_e_status(bot, queue):
    queue['jobs'] = [
        ['j1', job('EMPRESA_A', 'sentinel', 'running')],
        ['j2', job('EMPRESA_B', 'relatorioppt', 'queued', narrative=True)],
    ]

    [embed] = bot._set_embed_from_queue()

    assert fields(embed) == {
        'Empresa': 'EMPRESA_A\nEMPRESA_B\n',
        'Tipo de solicitação': 'Sentinela\nRelatório :flag_us:\n',
        'Status': 'Processando\nNa fila\n',
    }


def test_ver_fila_pagina_de_10_em_10(bot, queue):
    queue['jobs'] = [[f'j{i}', job(f'EMPRESA_{i}')] for i in range(23)]

    embeds = bot._set_embed_from_queue()

    assert len(embeds) == 3
    assert fields(embeds[0])['Empresa'].count('\n') == 10
    assert fields(embeds[2])['Empresa'].count('\n') == 3


@pytest.mark.parametrize('type_proccess, pretty', [
    ('storage', 'Storage'), ('fivepagefirst', '5page'), ('fivepagesecond', '5page'),
])
def test_ver_fila_com_storage_ou_5page(bot, queue, type_proccess, pretty):
    # antes da correção, o dicionário tinha 'sorage' e /ver_fila quebrava com KeyError
    queue['jobs'] = [['j1', job('EMPRESA_A', type_proccess)]]

    [embed] = bot._set_embed_from_queue()

    assert fields(embed)['Empresa'] == 'EMPRESA_A\n'
    assert fields(embed)['Tipo de solicitação'] == f'{pretty}\n'


def test_ver_fila_com_job_do_pipe_mostra_a_operadora(bot, queue):
    # job do Pipe: sem company_name nem narrative
    queue['jobs'] = [['j1', {'status': 'queued', 'type_proccess': 'pipe', 'operator': 'AMIL', 'cards_id': ['c1']}]]

    [embed] = bot._set_embed_from_queue()

    assert fields(embed) == {'Empresa': 'AMIL\n', 'Tipo de solicitação': 'Pipe\n', 'Status': 'Na fila\n'}


def test_ver_fila_com_tipo_desconhecido_mostra_o_nome_cru(bot, queue):
    queue['jobs'] = [['j1', job('EMPRESA_A', 'tipo_novo')]]

    [embed] = bot._set_embed_from_queue()

    assert fields(embed)['Tipo de solicitação'] == 'tipo_novo\n'


# --- /remover_fila ----------------------------------------------------------------

def test_remover_fila_cancela_todos_os_jobs_da_empresa(bot, queue):
    queue['jobs'] = [
        ['j1', job('EMPRESA_A')],
        ['j2', job('EMPRESA_B')],
        ['j3', job('EMPRESA_A', 'relatorioppt')],
    ]

    assert bot._cancel_company_from_firestore(' empresa_a ') is True
    assert queue['cancelled'] == ['j1', 'j3']


def test_remover_fila_varias_empresas(bot, queue):
    queue['jobs'] = [['j1', job('EMPRESA_A')], ['j2', job('EMPRESA_B')]]

    assert bot._cancel_company_from_firestore('empresa_a, empresa_b') is True
    assert queue['cancelled'] == ['j1', 'j2']


def test_remover_fila_empresa_que_nao_esta_na_fila(bot, queue):
    queue['jobs'] = [['j1', job('EMPRESA_A')]]

    assert bot._cancel_company_from_firestore('empresa_x') is False
    assert queue['cancelled'] == []


def test_remover_fila_com_a_fila_vazia(bot, queue):
    # antes da correção, o ManagerQueue devolvia None e o laço quebrava com TypeError
    assert bot._cancel_company_from_firestore('empresa_a') is False


def test_remover_fila_ignora_jobs_do_pipe(bot, queue):
    queue['jobs'] = [
        ['j1', {'status': 'queued', 'type_proccess': 'pipe', 'operator': 'AMIL'}],
        ['j2', job('EMPRESA_A')],
    ]

    assert bot._cancel_company_from_firestore('empresa_a') is True
    assert queue['cancelled'] == ['j2']


# --- webhook ------------------------------------------------------------------------

@pytest.fixture
def posts(monkeypatch, fake_response):
    calls = []

    def fake_post(url, json, headers):
        calls.append((url, json))
        return fake_response(204)

    monkeypatch.setattr(discord_app.requests, 'post', fake_post)
    return calls


def test_webhook_padrao_recebe_a_mensagem(bot, posts):
    bot.send_to_webhook('RabbitMQ fora do ar')

    assert posts == [('https://webhook.invalid/padrao', {'username': 'SuriDock', 'content': 'RabbitMQ fora do ar'})]


def test_webhook_explicito_recebe_a_mensagem(bot, posts):
    # antes da correção, o envio ficava dentro do "if not webhook" e nada era enviado
    bot.send_to_webhook('mensagem', webhook='https://webhook.invalid/outro')

    assert posts == [('https://webhook.invalid/outro', {'username': 'SuriDock', 'content': 'mensagem'})]
