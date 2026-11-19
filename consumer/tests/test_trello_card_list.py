"""Consulta da lista atual de um card no Trello (usada para respeitar o card movido à mão)."""
import pytest

from extensions import trello


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


def test_devolve_o_nome_da_lista(monkeypatch):
    calls = []

    def fake_get(url, params, timeout):
        calls.append((url, params['fields']))
        return FakeResponse(200, {'name': 'Operação: Finalizados'})

    monkeypatch.setattr(trello.requests, 'get', fake_get)

    assert trello.get_card_list_name('card-1') == 'Operação: Finalizados'
    assert calls == [('https://api.trello.com/1/cards/card-1/list', 'name')]


@pytest.mark.parametrize('response', [FakeResponse(404), FakeResponse(429)])
def test_erro_do_trello_devolve_none(monkeypatch, response):
    monkeypatch.setattr(trello.requests, 'get', lambda url, params, timeout: response)

    assert trello.get_card_list_name('card-1') is None


def test_falha_de_rede_devolve_none(monkeypatch):
    def boom(url, params, timeout):
        raise ConnectionError('sem rede')

    monkeypatch.setattr(trello.requests, 'get', boom)

    assert trello.get_card_list_name('card-1') is None
