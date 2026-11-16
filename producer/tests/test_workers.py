"""Rotinas em segundo plano do producer: limpeza da fila, segunda fase do 5Page,
Pipe diário e consultas da fila usadas pelo Discord."""
from datetime import datetime, timedelta

import pytest

import clear_queue
from apps import listener, pipe
from extensions import manager_queue


@pytest.fixture(autouse=True)
def use_fake_firestore(monkeypatch, firestore):
    for module in (clear_queue, listener, manager_queue):
        monkeypatch.setattr(module, 'GoogleFirestore', firestore)
    return firestore


# --- ClearQueue (de hora em hora) ----------------------------------------------

def test_clear_queue_apaga_so_jobs_terminados(firestore):
    firestore.tables['jobs'] = {
        'j-failed': {'status': 'failed'},
        'j-cancelled': {'status': 'cancelled'},
        'j-completed': {'status': 'completed'},
        'j-queued': {'status': 'queued'},
        'j-running': {'status': 'running'},
    }

    clear_queue.ClearQueue().run()

    assert firestore.batches == [('jobs', ['j-failed', 'j-cancelled', 'j-completed'])]


def test_clear_queue_sem_nada_para_apagar_nao_chama_o_batch(firestore):
    firestore.tables['jobs'] = {'j-queued': {'status': 'queued'}}

    clear_queue.ClearQueue().run()

    assert firestore.batches == []


# --- FivePage (segunda fase, verificada a cada minuto) -------------------------

class FakeTimestamp:
    """O Firestore devolve um DatetimeWithNanoseconds; o código só usa .timestamp()."""
    def __init__(self, moment):
        self.moment = moment

    def timestamp(self):
        return self.moment.timestamp()


def test_segunda_fase_do_5page_vai_para_a_fila_quando_chega_a_hora(firestore, produced):
    message = {'status': 'queued', 'type_proccess': 'fivepagesecond', 'company_name': 'EMPRESA_A'}
    firestore.tables['FivePage'] = {
        'job-vencido': {'time_to_run': FakeTimestamp(datetime.now() - timedelta(minutes=1)), 'message_json': message},
        'job-futuro': {'time_to_run': FakeTimestamp(datetime.now() + timedelta(minutes=10)), 'message_json': message},
    }

    listener.FivePage().run()

    # mantém o mesmo id do job: o card do Discord é atualizado em vez de criar outro
    assert produced == [{'job_id': 'job-vencido', **message}]
    assert firestore.deletes == [('FivePage', 'job-vencido')]


def test_segunda_fase_sem_agendamentos_nao_faz_nada(firestore, produced):
    listener.FivePage().run()

    assert produced == []
    assert firestore.deletes == []


# --- Pipe (uma vez por dia) ----------------------------------------------------

@pytest.fixture
def pipe_env(monkeypatch):
    state = {'cards': [], 'companies': {}, 'lists_asked': []}

    class FakeTrello:
        def __init__(self, list_source_name, list_target_name=None):
            state['lists_asked'].append(list_source_name)

        def get_list_id_by_name(self):
            return 'lista-pipe'

        def trello_list_cards(self, list_id):
            assert list_id == 'lista-pipe'
            return state['cards']

    class FakeApi:
        def get_company_by_id(self, company_id):
            return state['companies'][company_id]

    monkeypatch.setattr(pipe, 'Trello', FakeTrello)
    monkeypatch.setattr(pipe, 'SuridataApi', FakeApi)
    monkeypatch.setattr(pipe, 'get_formated_time_now', lambda: '16/11/2026 10:00:00')
    return state


def test_pipe_agrupa_os_cards_por_operadora(pipe_env, produced):
    pipe_env['companies'] = {
        '10': {'operator': {'name': 'AMIL'}},
        '20': {'operator': {'name': 'BRADESCO'}},
        '30': {'operator': {'name': 'AMIL'}},
    }
    pipe_env['cards'] = [
        {'id': 'c1', 'name': '10 - EMPRESA_A'},
        {'id': 'c2', 'name': '20 - EMPRESA_B'},
        {'id': 'c3', 'name': '30 - EMPRESA_C'},
    ]

    pipe.Pipe().run()

    assert pipe_env['lists_asked'] == ['Pipe: Processamento']
    assert produced == [
        {'job_id': None, 'status': 'queued', 'type_proccess': 'pipe', 'created_at': '16/11/2026 10:00:00',
         'operator': 'AMIL', 'cards_id': ['c1', 'c3']},
        {'job_id': None, 'status': 'queued', 'type_proccess': 'pipe', 'created_at': '16/11/2026 10:00:00',
         'operator': 'BRADESCO', 'cards_id': ['c2']},
    ]


def test_pipe_sem_cards_nao_cria_job(pipe_env, produced):
    pipe.Pipe().run()

    assert produced == []


# --- ManagerQueue (/ver_fila e /remover_fila) ----------------------------------

def test_fila_lista_so_jobs_na_fila_ou_rodando(firestore):
    firestore.tables['jobs'] = {
        'j1': {'status': 'queued'},
        'j2': {'status': 'running'},
        'j3': {'status': 'failed'},
    }

    assert manager_queue.ManagerQueue().get_queued_and_running() == [
        ['j1', {'status': 'queued'}],
        ['j2', {'status': 'running'}],
    ]


def test_fila_vazia_devolve_none(firestore):
    firestore.tables['jobs'] = {'j3': {'status': 'completed'}}

    assert manager_queue.ManagerQueue().get_queued_and_running() is None


def test_cancelar_job_marca_cancelled(firestore):
    manager_queue.ManagerQueue().cancel_job('j1')

    assert firestore.sets == [('jobs', 'j1', {'status': 'cancelled'})]
