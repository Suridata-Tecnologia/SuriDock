"""Mensagens do Discord levam a VM e o agente que estão processando o job."""
import json

import pytest

import common
import consumer


class FakeChannel:
    def __init__(self):
        self.published = []

    def queue_declare(self, **kwargs):
        pass

    def basic_publish(self, exchange, routing_key, body, properties=None):
        self.published.append((routing_key, json.loads(body.decode('utf-8'))))


class FakeConnection:
    def close(self):
        pass


@pytest.fixture
def channel(monkeypatch):
    fake = FakeChannel()
    monkeypatch.setattr(common, 'connection_rabbitmq', lambda: (fake, FakeConnection()))
    monkeypatch.setattr(common, 'CURRENT_AGENT', None)
    monkeypatch.setattr(common, 'LOCAL_MODE', False)
    return fake


def published(channel):
    [(routing_key, body)] = channel.published
    assert routing_key == common.RABBITMQ_MESSAGES
    return body


def test_mensagem_leva_vm_e_agente(channel):
    common.set_current_agent(2)

    common.publish_message_discord({'message_id': 'job-1', 'stage': 'baixando'})

    assert published(channel) == {'message_id': 'job-1', 'stage': 'baixando', 'agent': 'produção 1 agent2'}


def test_nao_altera_o_dicionario_de_quem_chamou(channel):
    common.set_current_agent(1)
    data = {'message_id': 'job-1'}

    common.publish_message_discord(data)

    assert data == {'message_id': 'job-1'}


def test_agente_informado_na_mensagem_prevalece(channel):
    common.set_current_agent(1)

    common.publish_message_discord({'message_id': 'job-1', 'agent': 'outro'})

    assert published(channel)['agent'] == 'outro'


def test_sem_agente_definido_a_mensagem_vai_sem_o_campo(channel):
    common.publish_message_discord({'message_id': 'job-1'})

    assert 'agent' not in published(channel)


def test_modo_local_nao_publica(channel):
    common.set_current_agent(1)
    common.set_local_mode()

    common.publish_message_discord({'message_id': 'job-1'})

    assert channel.published == []


@pytest.mark.parametrize('machine, expected', [('produção 4', 'produção 4 agent1'), (None, 'agent1'), ('', 'agent1')])
def test_agent_label(monkeypatch, machine, expected):
    monkeypatch.setattr(common, 'MACHINE_NAME', machine)

    assert common.agent_label(1) == expected


def test_agent_label_usa_o_agente_do_processo(monkeypatch):
    monkeypatch.setattr(common, 'CURRENT_AGENT', 3)

    assert common.agent_label() == 'produção 1 agent3'
    assert common.agent_label(None) == 'produção 1 agent3'


def test_start_consumer_registra_o_agente_do_processo(monkeypatch):
    monkeypatch.setattr(common, 'CURRENT_AGENT', None)

    class Stop(Exception):
        pass

    def stop():
        raise Stop

    monkeypatch.setattr(consumer, 'get_next_message', stop)

    with pytest.raises(Stop):
        consumer.start_consumer(4)

    assert common.CURRENT_AGENT == 4
