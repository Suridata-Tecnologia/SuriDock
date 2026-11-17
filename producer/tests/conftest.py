"""Configuração comum dos testes do producer.

Os testes nunca falam com serviços reais: as variáveis de ambiente são falsas e
RabbitMQ, MySQL, Firestore, Google Drive, Trello e Discord são bloqueados ou
substituídos por dublês. Cada teste roda numa pasta temporária.
"""
import os
import sys
from pathlib import Path

import pytest


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / 'scripts'

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# Valores falsos definidos antes de qualquer import do producer.
_ENV_DE_TESTE = {
    'RABBITMQ_HOST': 'rabbitmq.invalid',
    'RABBITMQ_USERNAME': 'teste',
    'RABBITMQ_PASSWORD': 'teste',
    'RABBITMQ_QUEUE': 'suridata_queue_teste',
    'RABBITMQ_MESSAGES': 'discord_messages_teste',
    'DRIVE_ID_QVD': 'drive-qvd-teste',
    'SURIDB_HOST': 'mysql.invalid',
    'SURIDB_USERNAME': 'teste',
    'SURIDB_PASSWORD': 'teste',
    'SURIDB_DATABASE': 'teste',
    'SURIDB_PORT': '3306',
    'SURI_API_TOKEN': 'teste',
    'SURI_TRELLO_API_KEY': 'chave-teste',
    'SURI_TRELLO_API_TOKEN': 'token-teste',
    'DISCORD_ID_CHANNEL_BOTS': '111',
    'DISCORD_ID_CHANNEL_SENTINEL': '222',
    'DISCORD_WEBHOOK': 'https://webhook.invalid/padrao',
    'DISCORD_TOKEN': 'teste',
}
os.environ.update(_ENV_DE_TESTE)


@pytest.fixture(autouse=True)
def isolated_cwd(tmp_path, monkeypatch):
    """Cada teste roda numa pasta temporária vazia (sem credentials/ de verdade)."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture(autouse=True)
def block_external_connections(monkeypatch):
    """Rede de segurança: falha alto se algum teste tentar conectar de verdade."""
    import mysql.connector
    import pika
    import requests
    from google.cloud import firestore

    def blocked(*args, **kwargs):
        raise RuntimeError('teste tentou abrir uma conexão real')

    monkeypatch.setattr(pika, 'BlockingConnection', blocked)
    monkeypatch.setattr(mysql.connector, 'connect', blocked)
    monkeypatch.setattr(firestore.Client, 'from_service_account_json', blocked)
    for method in ('get', 'post', 'put', 'delete'):
        monkeypatch.setattr(requests, method, blocked)


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=''):
        self.status_code = status_code
        self._json = json_data
        self.text = text

    def json(self):
        return self._json


@pytest.fixture
def fake_response():
    return FakeResponse


class FakeFirestore:
    """Dublê do GoogleFirestore: guarda tudo em memória, por tabela."""
    tables = {}
    sets = []
    deletes = []
    batches = []

    def __init__(self, table):
        self.table = table
        FakeFirestore.tables.setdefault(table, {})

    def get_all_jobs(self):
        return dict(FakeFirestore.tables[self.table])

    def set_job(self, job_id, data, merge=True):
        FakeFirestore.sets.append((self.table, job_id, data))

    def delete_job(self, job_id):
        FakeFirestore.deletes.append((self.table, job_id))
        return True

    def delete_jobs_batch(self, job_ids):
        FakeFirestore.batches.append((self.table, list(job_ids)))
        return len(job_ids)


@pytest.fixture
def firestore():
    FakeFirestore.tables = {}
    FakeFirestore.sets = []
    FakeFirestore.deletes = []
    FakeFirestore.batches = []
    return FakeFirestore


@pytest.fixture
def produced(monkeypatch):
    """Substitui o Producer (Firestore + RabbitMQ) e registra o que seria enviado."""
    import common

    calls = []

    class FakeProducer:
        def __init__(self, message_data, job_id=None):
            self.message_data = message_data
            self.job_id = job_id

        def run(self):
            calls.append({'job_id': self.job_id, **self.message_data})

    monkeypatch.setattr(common, 'Producer', FakeProducer)
    # módulos que já fizeram "from common import Producer" / "import *"
    for name in ('apps.listener', 'apps.pipe', 'extensions.five_page', 'extensions.storage',
                 'extensions.relatorio_ppt', 'extensions.trello'):
        module = sys.modules.get(name)
        if module is not None and hasattr(module, 'Producer'):
            monkeypatch.setattr(module, 'Producer', FakeProducer)
    return calls
