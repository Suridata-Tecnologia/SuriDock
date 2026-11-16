"""consumer.py: leitura da fila, processamento e retentativas (P37)."""
import json
from types import SimpleNamespace

import pytest

import common
import consumer


class FakeChannel:
    def __init__(self, results=None, publish_error=None, get_error=None):
        self.results = list(results or [])
        self.publish_error = publish_error
        self.get_error = get_error
        self.published = []
        self.acked = []
        self.declared = []
        self.get_calls = 0

    def queue_declare(self, queue, durable):
        self.declared.append((queue, durable))

    def basic_get(self, queue, auto_ack):
        self.get_calls += 1
        assert auto_ack is False
        if self.get_error:
            raise self.get_error
        if self.results:
            return self.results.pop(0)
        return None, None, None

    def basic_ack(self, delivery_tag):
        self.acked.append(delivery_tag)

    def basic_publish(self, exchange, routing_key, body, properties=None):
        if self.publish_error:
            raise self.publish_error
        self.published.append({
            'exchange': exchange,
            'routing_key': routing_key,
            'body': body,
            'properties': properties,
        })


class FakeConnection:
    def __init__(self):
        self.closed = False
        self.sleeps = 0

    def sleep(self, seconds):
        self.sleeps += 1

    def close(self):
        self.closed = True


def fake_rabbit(monkeypatch, channel):
    connection = FakeConnection()
    monkeypatch.setattr(consumer, 'connection_rabbitmq', lambda: (channel, connection))
    return connection


def message(job_id='job-1', retry_count=None, delivery_tag=7):
    headers = {'x-retry-count': retry_count} if retry_count is not None else None
    method = SimpleNamespace(delivery_tag=delivery_tag)
    properties = SimpleNamespace(headers=headers)
    body = json.dumps({'job_id': job_id}).encode('utf-8')
    return method, properties, body


# --- requeue_message ---------------------------------------------------------

def test_republica_com_o_contador_incrementado(monkeypatch):
    channel = FakeChannel()
    connection = fake_rabbit(monkeypatch, channel)
    body = b'{"job_id": "job-1"}'

    consumer.requeue_message(1, 'job-1', {'outro': 'valor'}, body)

    assert len(channel.published) == 1
    published = channel.published[0]
    assert published['routing_key'] == consumer.RABBITMQ_QUEUE
    assert published['body'] == body
    assert published['properties'].headers == {
        'outro': 'valor', 'x-retry-count': 2, 'disc_message_id': 'job-1'
    }
    assert connection.closed


def test_descarta_o_job_na_quinta_tentativa(monkeypatch):
    def must_not_connect():
        raise AssertionError('não deveria republicar')

    monkeypatch.setattr(consumer, 'connection_rabbitmq', must_not_connect)

    consumer.requeue_message(consumer.MAX_RETRIES - 1, 'job-1', {}, b'{}')


def test_tenta_republicar_tres_vezes_e_desiste(monkeypatch):
    attempts = []

    def failing_connection():
        attempts.append(1)
        raise ConnectionError('rabbit fora do ar')

    monkeypatch.setattr(consumer, 'connection_rabbitmq', failing_connection)
    monkeypatch.setattr(consumer, 'sleep', lambda seconds: None)

    consumer.requeue_message(0, 'job-1', {}, b'{}')

    assert len(attempts) == 3


def test_fecha_a_conexao_mesmo_quando_a_publicacao_falha(monkeypatch):
    channel = FakeChannel(publish_error=RuntimeError('canal fechado'))
    connection = fake_rabbit(monkeypatch, channel)
    monkeypatch.setattr(consumer, 'sleep', lambda seconds: None)

    consumer.requeue_message(0, 'job-1', {}, b'{}')

    assert connection.closed
    assert channel.published == []


# --- get_next_message --------------------------------------------------------

def test_confirma_a_mensagem_antes_de_devolver(monkeypatch):
    method, properties, body = message(delivery_tag=42)
    channel = FakeChannel(results=[(method, properties, body)])
    connection = fake_rabbit(monkeypatch, channel)
    monkeypatch.setattr(consumer, 'restart_pending', lambda: False)

    got_properties, got_body = consumer.get_next_message()

    assert (got_properties, got_body) == (properties, body)
    assert channel.acked == [42]
    assert channel.declared == [(consumer.RABBITMQ_QUEUE, True)]
    assert connection.closed


def test_fila_vazia_espera_e_tenta_de_novo(monkeypatch):
    msg = message()
    channel = FakeChannel(results=[(None, None, None), (None, None, None), msg])
    connection = fake_rabbit(monkeypatch, channel)
    monkeypatch.setattr(consumer, 'restart_pending', lambda: False)

    consumer.get_next_message()

    assert channel.get_calls == 3
    assert connection.sleeps == 2


def test_nao_pega_jobs_com_reinicio_pendente(monkeypatch):
    channel = FakeChannel(results=[message()])
    connection = fake_rabbit(monkeypatch, channel)
    pending = iter([True, True, False])
    monkeypatch.setattr(consumer, 'restart_pending', lambda: next(pending))

    consumer.get_next_message()

    assert channel.get_calls == 1
    assert connection.sleeps == 2


def test_fecha_a_conexao_quando_a_leitura_falha(monkeypatch):
    channel = FakeChannel(get_error=ConnectionError('conexão perdida'))
    connection = fake_rabbit(monkeypatch, channel)
    monkeypatch.setattr(consumer, 'restart_pending', lambda: False)

    with pytest.raises(ConnectionError):
        consumer.get_next_message()

    assert connection.closed


# --- process_message ---------------------------------------------------------

@pytest.fixture
def fake_start(monkeypatch):
    class FakeStartProcess:
        result = True
        error = None
        calls = []
        state_during_run = []

        def __init__(self, agent_number, retry_count, job_id):
            FakeStartProcess.calls.append((agent_number, retry_count, job_id))
            self.agent_number = agent_number

        def run(self):
            FakeStartProcess.state_during_run.append(
                common.read_agent_states()[self.agent_number - 1]
            )
            if FakeStartProcess.error:
                raise FakeStartProcess.error
            return FakeStartProcess.result

    FakeStartProcess.calls = []
    FakeStartProcess.state_during_run = []
    monkeypatch.setattr(consumer, 'StartProcess', FakeStartProcess)
    return FakeStartProcess


@pytest.fixture
def requeued(monkeypatch):
    calls = []
    monkeypatch.setattr(consumer, 'requeue_message', lambda *args: calls.append(args))
    return calls


def test_sucesso_nao_recoloca_na_fila(fake_start, requeued):
    _, properties, body = message('job-ok', retry_count=2)

    consumer.process_message(properties, body, agent_number=1)

    assert fake_start.calls == [(1, 2, 'job-ok')]
    assert requeued == []


def test_agente_fica_running_durante_o_job_e_stopped_depois(fake_start, requeued):
    _, properties, body = message()

    consumer.process_message(properties, body, agent_number=2)

    assert fake_start.state_during_run == ['agent2-running']
    assert common.read_agent_states()[1] == 'agent2-stopped'


def test_falha_recoloca_na_fila_com_os_mesmos_dados(fake_start, requeued):
    fake_start.result = False
    _, properties, body = message('job-falha', retry_count=1)

    consumer.process_message(properties, body, agent_number=1)

    assert requeued == [(1, 'job-falha', {'x-retry-count': 1}, body)]


def test_excecao_no_job_conta_como_falha_e_libera_o_agente(fake_start, requeued):
    fake_start.error = RuntimeError('qlik travou')
    _, properties, body = message('job-erro')

    consumer.process_message(properties, body, agent_number=1)

    assert len(requeued) == 1
    assert common.read_agent_states()[0] == 'agent1-stopped'


def test_sem_headers_considera_primeira_tentativa(fake_start, requeued):
    fake_start.result = False
    _, properties, body = message('job-novo')  # headers=None

    consumer.process_message(properties, body, agent_number=1)

    assert fake_start.calls == [(1, 0, 'job-novo')]
    assert requeued[0][0] == 0


@pytest.mark.parametrize('body', [b'nao e json', b'{"outro": 1}', b'\xff\xfe'])
def test_mensagem_invalida_e_descartada_sem_processar(fake_start, requeued, body):
    consumer.process_message(SimpleNamespace(headers=None), body, agent_number=1)

    assert fake_start.calls == []
    assert requeued == []
