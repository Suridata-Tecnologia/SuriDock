"""Trello: leitura das listas a cada 15 s, criação dos jobs e chamadas à API do Trello."""
from datetime import datetime, time

import pytest

from extensions import trello as trello_module


class StopWatcher(BaseException):
    """Interrompe o laço infinito do _trello_watcher. É BaseException para escapar
    do 'except Exception' do próprio laço."""


def make_trello(source, target='Lista destino'):
    # criado sem destino para não iniciar a thread; o destino é definido depois
    trello = trello_module.Trello(source)
    trello.list_target_name = target
    return trello


# --- API do Trello --------------------------------------------------------------

def test_get_list_id_ignora_maiusculas_e_espacos(monkeypatch, fake_response):
    calls = []

    def fake_get(url, params):
        calls.append((url, params))
        return fake_response(200, [{'id': 'l1', 'name': 'Outra'}, {'id': 'l2', 'name': ' Operação: Processamento '}])

    monkeypatch.setattr(trello_module.requests, 'get', fake_get)

    assert trello_module.Trello('operação: processamento').get_list_id_by_name() == 'l2'
    url, params = calls[0]
    assert url == 'https://api.trello.com/1/boards/Vlpk9mpl/lists'
    assert params == {'key': 'chave-teste', 'token': 'token-teste'}


def test_get_list_id_por_nome_explicito(monkeypatch, fake_response):
    monkeypatch.setattr(trello_module.requests, 'get',
                        lambda url, params: fake_response(200, [{'id': 'l9', 'name': 'Destino'}]))

    assert trello_module.Trello('Origem').get_list_id_by_name('destino') == 'l9'


@pytest.mark.parametrize('response', [
    'status_500', 'lista_inexistente', 'excecao',
])
def test_get_list_id_devolve_none_quando_nao_consegue(monkeypatch, fake_response, response):
    def fake_get(url, params):
        if response == 'excecao':
            raise ConnectionError('sem rede')
        if response == 'status_500':
            return fake_response(500, text='erro')
        return fake_response(200, [{'id': 'l1', 'name': 'Outra'}])

    monkeypatch.setattr(trello_module.requests, 'get', fake_get)

    assert trello_module.Trello('Origem').get_list_id_by_name() is None


def test_trello_list_cards(monkeypatch, fake_response):
    monkeypatch.setattr(trello_module.requests, 'get',
                        lambda url, params: fake_response(200, [{'id': 'c1'}]) if url.endswith('/lists/l1/cards') else None)

    assert trello_module.Trello('Origem').trello_list_cards('l1') == [{'id': 'c1'}]


@pytest.mark.parametrize('error', ['status', 'excecao'])
def test_trello_list_cards_com_erro_devolve_lista_vazia(monkeypatch, fake_response, error):
    def fake_get(url, params):
        if error == 'excecao':
            raise ConnectionError('sem rede')
        return fake_response(401, text='unauthorized')

    monkeypatch.setattr(trello_module.requests, 'get', fake_get)

    assert trello_module.Trello('Origem').trello_list_cards('l1') == []


def test_trello_move_card(monkeypatch, fake_response):
    calls = []
    monkeypatch.setattr(trello_module.requests, 'put',
                        lambda url, params: calls.append((url, params)) or fake_response(200))

    trello_module.Trello('Origem').trello_move_card('card-1', 'lista-2')

    assert calls == [('https://api.trello.com/1/cards/card-1',
                      {'idList': 'lista-2', 'key': 'chave-teste', 'token': 'token-teste'})]


def test_trello_move_card_com_erro_nao_levanta(monkeypatch, fake_response):
    monkeypatch.setattr(trello_module.requests, 'put', lambda url, params: fake_response(404, text='card não existe'))

    trello_module.Trello('Origem').trello_move_card('card-1', 'lista-2')


# --- janela de horário ----------------------------------------------------------

@pytest.fixture
def clock(monkeypatch):
    state = {'now': time(12, 0)}

    class FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 16, state['now'].hour, state['now'].minute)

    monkeypatch.setattr(trello_module, 'datetime', FakeDatetime)
    return state


@pytest.mark.parametrize('now, expected', [
    (time(19, 0), True), (time(23, 30), True), (time(0, 0), True), (time(4, 0), True),
    (time(4, 1), False), (time(12, 0), False), (time(18, 59), False),
])
def test_janela_do_storage_atravessa_a_meia_noite(clock, now, expected):
    clock['now'] = now

    assert trello_module.Trello('Origem').can_read_trello('storage') is expected


@pytest.mark.parametrize('now, expected', [
    (time(5, 0), True), (time(12, 0), True), (time(18, 0), True),
    (time(4, 59), False), (time(18, 1), False), (time(23, 0), False),
])
def test_janela_do_5page(clock, now, expected):
    clock['now'] = now

    assert trello_module.Trello('Origem').can_read_trello('5page') is expected


def test_modo_test_ignora_a_janela(clock):
    clock['now'] = time(12, 0)

    assert trello_module.Trello('Origem').can_read_trello('storage', test=True) is True


def test_modo_desconhecido_levanta_erro(clock):
    """Documenta o comportamento atual: um modo fora de 'storage'/'5page' não tem
    janela definida e quebra com UnboundLocalError."""
    with pytest.raises(UnboundLocalError):
        trello_module.Trello('Origem').can_read_trello('sentinel')


# --- _trello_watcher: card na lista de entrada vira job ----------------------------

@pytest.fixture
def watcher(monkeypatch, produced):
    state = {'cards': [], 'moved': [], 'english': False, 'sleeps': [], 'list_ids': {}, 'db_calls': []}

    class FakeApi:
        def get_company_by_id(self, company_id):
            return {'drive_folder': f'EMPRESA_{company_id}'}

    class FakeDatabase:
        def get_language_by_company(self, company_name):
            state['db_calls'].append(company_name)
            return state['english']

    def fake_sleep(seconds):
        state['sleeps'].append(seconds)
        raise StopWatcher

    monkeypatch.setattr(trello_module, 'SuridataApi', FakeApi)
    monkeypatch.setattr(trello_module, 'Database', FakeDatabase)
    monkeypatch.setattr(trello_module, 'sleep', fake_sleep)
    monkeypatch.setattr(trello_module, 'get_formated_time_now', lambda: '16/11/2026 10:00:00')
    monkeypatch.setattr(trello_module.Trello, 'get_list_id_by_name',
                        lambda self, name='': state['list_ids'].get(name, f'id:{name}'))
    monkeypatch.setattr(trello_module.Trello, 'trello_list_cards', lambda self, list_id: state['cards'])
    monkeypatch.setattr(trello_module.Trello, 'trello_move_card',
                        lambda self, card_id, list_id: state['moved'].append((card_id, list_id)))

    def run(source, target='Lista destino'):
        with pytest.raises(StopWatcher):
            make_trello(source, target)._trello_watcher()

    state['run'] = run
    state['produced'] = produced
    return state


CARD = {'id': 'card-1', 'name': '1406 - BIOAGRI_AMIL'}


@pytest.mark.parametrize('source, type_proccess', [
    ('Operação: Aguardando Processamento', 'sentinel'),
    ('Operação: Atualizar no Portal (Storage) 🎉', 'storage'),
    ('Qualidade: Upload 6M', 'fivepagefirst'),
])
def test_card_vira_job_do_tipo_da_lista(watcher, source, type_proccess):
    watcher['cards'] = [CARD]

    watcher['run'](source, 'Destino')

    assert watcher['moved'] == [('card-1', 'id:Destino')]
    [job] = watcher['produced']
    assert job['type_proccess'] == type_proccess
    assert job['status'] == 'queued'
    assert job['company_name'] == 'EMPRESA_1406'
    assert job['company_id'] == '1406'
    assert job['trello_card_id'] == 'card-1'
    assert job['discord_username'] == 'Trello - Card 1406'
    assert job['created_at'] == '16/11/2026 10:00:00'
    assert watcher['sleeps'] == [15]


def test_5page_do_trello_usa_capa_clara(watcher):
    watcher['cards'] = [CARD]

    watcher['run']('Qualidade: Upload 6M')

    assert watcher['produced'][0]['dark_mode'] is False


def test_relatorio_de_empresa_com_ingles_gera_dois_jobs(watcher):
    watcher['cards'] = [CARD]
    watcher['english'] = True

    watcher['run']('Qualidade: Processar PPT')

    assert watcher['db_calls'] == ['EMPRESA_1406']
    assert [job['narrative'] for job in watcher['produced']] == [False, True]
    assert all(job['type_proccess'] == 'relatorioppt' for job in watcher['produced'])
    assert all(job['month_analysis'] == 'não' and job['audith'] is False for job in watcher['produced'])


def test_relatorio_de_empresa_so_em_portugues_gera_um_job(watcher):
    watcher['cards'] = [CARD]

    watcher['run']('Qualidade: Processar PPT')

    assert [job['narrative'] for job in watcher['produced']] == [False]


def test_varios_cards_na_mesma_rodada(watcher):
    watcher['cards'] = [CARD, {'id': 'card-2', 'name': '878 - JWM_AMIL'}]

    watcher['run']('Qualidade: Upload 6M')

    assert [job['company_id'] for job in watcher['produced']] == ['1406', '878']
    assert [card for card, _ in watcher['moved']] == ['card-1', 'card-2']


def test_lista_vazia_so_espera_a_proxima_rodada(watcher):
    watcher['run']('Qualidade: Upload 6M')

    assert watcher['produced'] == []
    assert watcher['sleeps'] == [15]


def test_lista_sem_tipo_conhecido_nao_cria_job(watcher):
    watcher['cards'] = [CARD]

    watcher['run']('Lista Qualquer')

    assert watcher['produced'] == []
    assert watcher['moved'] == []


def test_sem_id_das_listas_tenta_de_novo_em_5s(watcher):
    watcher['list_ids'] = {'Qualidade: Upload 6M': None}
    watcher['cards'] = [CARD]

    watcher['run']('Qualidade: Upload 6M')

    assert watcher['sleeps'] == [5]
    assert watcher['produced'] == []


def test_erro_num_card_interrompe_a_rodada_e_tenta_de_novo(watcher, monkeypatch):
    """Documenta o comportamento atual: um card com erro (ex.: a API não acha a empresa)
    faz o laço pular os cards seguintes daquela rodada."""
    class BrokenApi:
        def get_company_by_id(self, company_id):
            if company_id == '999':
                raise KeyError('data')
            return {'drive_folder': f'EMPRESA_{company_id}'}

    monkeypatch.setattr(trello_module, 'SuridataApi', BrokenApi)
    watcher['cards'] = [{'id': 'card-x', 'name': '999 - SEM_CADASTRO'}, CARD]

    watcher['run']('Qualidade: Upload 6M')

    assert watcher['produced'] == []
    assert watcher['sleeps'] == [15]


def test_card_e_movido_antes_de_criar_o_job(watcher, monkeypatch):
    """Se o Producer falhar, o card já saiu da lista de entrada e não é lido de novo."""
    order = []
    monkeypatch.setattr(trello_module.Trello, 'trello_move_card',
                        lambda self, card_id, list_id: order.append('move'))

    class RecordingProducer:
        def __init__(self, data, job_id=None):
            pass

        def run(self):
            order.append('produce')

    monkeypatch.setattr(trello_module, 'Producer', RecordingProducer)
    watcher['cards'] = [CARD]

    watcher['run']('Qualidade: Upload 6M')

    assert order == ['move', 'produce']
