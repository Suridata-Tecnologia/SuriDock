"""Disponibilidade do Qlik: hub na porta 4848, reabertura e trava entre agentes."""
from contextlib import contextmanager

import pytest
import requests

import common


class FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code


@pytest.fixture
def no_sleep(monkeypatch):
    sleeps = []
    monkeypatch.setattr(common, 'sleep', lambda seconds: sleeps.append(seconds))
    return sleeps


# --- wait_qlik_hub -----------------------------------------------------------

def test_hub_respondendo_retorna_na_hora(monkeypatch, no_sleep):
    calls = []
    monkeypatch.setattr(common.requests, 'get', lambda url, timeout: calls.append(url) or FakeResponse(200))

    assert common.wait_qlik_hub(timeout=30) is True
    assert calls == ['http://localhost:4848/hub/my/work']
    assert no_sleep == []


def test_hub_fora_do_ar_ate_o_tempo_acabar(monkeypatch, no_sleep):
    calls = []

    def refused(url, timeout):
        calls.append(url)
        raise requests.ConnectionError('conexão recusada')

    monkeypatch.setattr(common.requests, 'get', refused)

    assert common.wait_qlik_hub(timeout=15) is False
    assert len(calls) == 3


def test_hub_que_volta_depois_de_um_erro_500(monkeypatch, no_sleep):
    responses = iter([FakeResponse(500), FakeResponse(200)])
    monkeypatch.setattr(common.requests, 'get', lambda url, timeout: next(responses))

    assert common.wait_qlik_hub(timeout=30) is True
    assert no_sleep == [5]


# --- ensure_qlik_ready -------------------------------------------------------

@pytest.fixture
def qlik(monkeypatch, no_sleep):
    """Substitui as peças do Qlik por dublês configuráveis."""
    state = {
        'hub': {},          # timeout -> resposta do wait_qlik_hub
        'window_open': False,
        'open_result': True,
        'open_error': None,
        'calls': [],
        'lock': [],
    }

    def wait_qlik_hub(timeout=180):
        state['calls'].append(('wait', timeout))
        return state['hub'].get(timeout, False)

    def is_qlik_running():
        state['calls'].append(('is_running',))
        return state['window_open']

    def close_process(name):
        state['calls'].append(('close', name))

    def open_and_start_qlik(agent_number):
        state['calls'].append(('open', agent_number))
        if state['open_error']:
            raise state['open_error']
        return state['open_result']

    @contextmanager
    def fake_lock(agent_number, timeout=900):
        state['lock'].append('enter')
        try:
            yield
        finally:
            state['lock'].append('exit')

    monkeypatch.setattr(common, 'wait_qlik_hub', wait_qlik_hub)
    monkeypatch.setattr(common, 'is_qlik_running', is_qlik_running)
    monkeypatch.setattr(common, 'close_process', close_process)
    monkeypatch.setattr(common, 'open_and_start_qlik', open_and_start_qlik)
    monkeypatch.setattr(common, 'qlik_start_lock', fake_lock)
    return state


def test_qlik_ja_aberto_nao_e_reaberto(qlik):
    qlik['hub'] = {5: True}

    assert common.ensure_qlik_ready(1) is True
    assert ('open', 1) not in qlik['calls']
    assert ('close', 'qlik') not in qlik['calls']
    assert qlik['lock'] == ['enter', 'exit']


def test_janela_aberta_aguarda_o_hub_terminar_de_subir(qlik):
    qlik['hub'] = {5: False, 60: True}
    qlik['window_open'] = True

    assert common.ensure_qlik_ready(1) is True
    assert ('close', 'qlik') not in qlik['calls']


def test_janela_aberta_sem_hub_fecha_e_reabre(qlik):
    qlik['hub'] = {5: False, 60: False, 10: True}
    qlik['window_open'] = True

    assert common.ensure_qlik_ready(2) is True
    assert qlik['calls'].index(('close', 'qlik')) < qlik['calls'].index(('open', 2))


def test_sem_janela_fecha_restos_e_abre_o_qlik(qlik):
    qlik['hub'] = {5: False, 10: True}

    assert common.ensure_qlik_ready(1) is True
    assert ('close', 'qlik') in qlik['calls']
    assert ('open', 1) in qlik['calls']


def test_falha_ao_abrir_o_qlik(qlik):
    qlik['open_result'] = False

    assert common.ensure_qlik_ready(1) is False


def test_qlik_abre_mas_o_hub_nao_responde(qlik):
    qlik['hub'] = {5: False, 10: False}

    assert common.ensure_qlik_ready(1) is False


def test_trava_e_liberada_mesmo_com_erro(qlik):
    qlik['open_error'] = RuntimeError('pywinauto falhou')

    with pytest.raises(RuntimeError):
        common.ensure_qlik_ready(1)

    assert qlik['lock'] == ['enter', 'exit']


# --- qlik_start_lock (trava real do Windows) ---------------------------------

def test_trava_pode_ser_reutilizada_depois_de_liberada(no_sleep):
    with common.qlik_start_lock(1):
        pass

    with common.qlik_start_lock(2, timeout=0):
        pass


def test_segundo_agente_espera_e_desiste_no_tempo_limite(no_sleep):
    with common.qlik_start_lock(1):
        with pytest.raises(TimeoutError):
            with common.qlik_start_lock(2, timeout=0):
                pass


def test_trava_liberada_quando_o_bloco_lanca_excecao(no_sleep):
    with pytest.raises(RuntimeError):
        with common.qlik_start_lock(1):
            raise RuntimeError('erro dentro da trava')

    with common.qlik_start_lock(2, timeout=0):
        pass
