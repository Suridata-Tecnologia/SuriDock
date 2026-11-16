"""Configuração comum dos testes do consumer.

Os testes nunca falam com serviços reais: as variáveis de ambiente são falsas,
o RabbitMQ e o MySQL são bloqueados e cada teste roda numa pasta temporária
(os caminhos do consumer, como config/ e logs/, são relativos à pasta atual).
"""
import os
import sys
from pathlib import Path

import pytest


CONSUMER_DIR = Path(__file__).resolve().parents[1]

# O consumer importa msvcrt e pywinauto, que só existem no Windows (como nas VMs).
if sys.platform != 'win32':
    collect_ignore_glob = ['test_*.py']

if str(CONSUMER_DIR) not in sys.path:
    sys.path.insert(0, str(CONSUMER_DIR))

# Valores falsos definidos antes de qualquer import do consumer. O load_dotenv não
# sobrescreve variáveis que já existem, então um .env real na pasta nunca é usado.
_ENV_DE_TESTE = {
    'MACHINE_NAME': 'produção 1',
    'RABBITMQ_HOST': 'rabbitmq.invalid',
    'RABBITMQ_USERNAME': 'teste',
    'RABBITMQ_PASSWORD': 'teste',
    'RABBITMQ_QUEUE': 'suridata_queue_teste',
    'RABBITMQ_MESSAGES': 'discord_messages_teste',
    'RABBITMQ_FIVEPAGE': 'fivepage_teste',
    'SURIDB_HOST': 'mysql.invalid',
    'SURIDB_USERNAME': 'teste',
    'SURIDB_PASSWORD': 'teste',
    'SURIDB_DATABASE': 'teste',
    'SURIDB_PORT': '3306',
    'SURIPORTAL_USERNAME': 'teste',
    'SURIPORTAL_PASSWORD': 'teste',
    'CAPTCHA_KEY': 'teste',
    'ADOBE_CLIENT_ID': 'teste',
    'ADOBE_CLIENT_SECRET': 'teste',
}
os.environ.update(_ENV_DE_TESTE)


@pytest.fixture(autouse=True)
def isolated_cwd(tmp_path, monkeypatch):
    """Cada teste roda numa pasta temporária vazia."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture(autouse=True)
def os_system_calls(monkeypatch):
    """Impede comandos reais (ex.: 'pm2 delete all') e registra o que seria executado."""
    calls = []

    def fake_system(command):
        calls.append(command)
        return 0

    monkeypatch.setattr(os, 'system', fake_system)
    return calls


@pytest.fixture(autouse=True)
def block_external_connections(monkeypatch):
    """Rede de segurança: falha alto se algum teste tentar conectar de verdade."""
    import mysql.connector
    import pika

    def blocked(*args, **kwargs):
        raise RuntimeError('teste tentou abrir uma conexão real (RabbitMQ ou MySQL)')

    monkeypatch.setattr(pika, 'BlockingConnection', blocked)
    monkeypatch.setattr(mysql.connector, 'connect', blocked)
