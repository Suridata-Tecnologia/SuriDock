"""5Page: agendamento da segunda fase, montagem da URL e entrega do PDF/PPTX no Drive.

A navegação no Looker Studio (Selenium) fica fora dos testes unitários.
"""
from datetime import datetime, timedelta

import pytest

import common
from extensions import five_page


class FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 3, 5, 10, 0, 0, tzinfo=tz)

    @classmethod
    def today(cls):
        return cls(2026, 3, 5, 10, 0, 0)


def job(**overrides):
    data = {
        'company_name': 'EMPRESA_TESTE',
        'company_id': 10,
        'discord_user_id': None,
        'discord_username': 'Trello - Card 1',
        'trello_card_id': 'card-1',
        'narrative': False,
        'created_at': '16/11/2026 10:00:00',
        'type_proccess': 'fivepagefirst',
        'status': 'running',
    }
    data.update(overrides)
    return data


# --- get_url_fivepage --------------------------------------------------------

def fake_database(monkeypatch, rows):
    class FakeDatabase:
        def find_pretty_name_and_operator_name(self, drive_folder):
            return rows

    monkeypatch.setattr(common, 'Database', FakeDatabase)


def test_monta_a_url_do_painel_em_base64(monkeypatch):
    fake_database(monkeypatch, [{'dashboard_param': 'Empresa Teste', 'id': 42}])

    url, pretty_name = common.get_url_fivepage('EMPRESA_TESTE')

    # 'NDI=' = '42', 'T25lIFBhZ2U=' = 'One Page', 'RW1wcmVzYSBUZXN0ZQ==' = 'Empresa Teste'
    assert url == 'https://portal.suridata.com.br/dashboard/NDI=/bmFu/T25lIFBhZ2U=/RW1wcmVzYSBUZXN0ZQ==/1'
    assert pretty_name == 'Empresa Teste'


def test_empresa_sem_cadastro_gera_index_error(monkeypatch):
    """Documenta o comportamento atual: empresa que não está no banco quebra antes de abrir
    o navegador, e o Discord mostra só 'Ocorreu um erro desconhecido' a 0%."""
    fake_database(monkeypatch, [])

    with pytest.raises(IndexError):
        common.get_url_fivepage('EMPRESA_INEXISTENTE')


# --- FivePageFirst -----------------------------------------------------------

@pytest.fixture
def first_env(monkeypatch):
    state = {'storage_result': True, 'storage_calls': 0, 'firestore': [], 'second_runs': 0}

    class FakeStorage:
        def __init__(self, *args):
            pass

        def run(self):
            state['storage_calls'] += 1
            return state['storage_result']

    class FakeFirestore:
        def __init__(self, table):
            self.table = table

        def set_job(self, job_id, data):
            state['firestore'].append((self.table, job_id, data))

    class FakeSecond:
        def __init__(self, *args):
            pass

        def run(self):
            state['second_runs'] += 1
            return True

    monkeypatch.setattr(five_page, 'Storage', FakeStorage)
    monkeypatch.setattr(five_page, 'GoogleFirestore', FakeFirestore)
    monkeypatch.setattr(five_page, 'FivePageSecond', FakeSecond)
    monkeypatch.setattr(five_page, 'is_local_mode', lambda: False)
    monkeypatch.setattr(five_page, 'datetime', FixedDatetime)
    return state


def test_pedido_do_trello_roda_storage_e_agenda_para_15_minutos(first_env):
    data = job()

    assert five_page.FivePageFirst(1, 0, 'job-1', data, '5page').run() is True

    assert first_env['storage_calls'] == 1
    table, job_id, scheduled = first_env['firestore'][0]
    assert (table, job_id) == ('FivePage', 'job-1')
    assert scheduled['time_to_run'] == FixedDatetime.now() + timedelta(minutes=15)
    assert scheduled['message_json']['type_proccess'] == 'fivepagesecond'
    assert scheduled['message_json']['status'] == 'queued'


def test_pedido_do_discord_pula_o_storage_e_agenda_para_agora(first_env):
    data = job(discord_user_id='123')

    assert five_page.FivePageFirst(1, 0, 'job-1', data, '5page').run() is True

    assert first_env['storage_calls'] == 0
    assert first_env['firestore'][0][2]['time_to_run'] == FixedDatetime.now()


def test_storage_que_falha_nao_agenda_a_segunda_fase(first_env):
    first_env['storage_result'] = False

    assert five_page.FivePageFirst(1, 0, 'job-1', job(), '5page').run() is False
    assert first_env['firestore'] == []


def test_modo_local_roda_a_segunda_fase_na_hora(first_env, monkeypatch):
    monkeypatch.setattr(five_page, 'is_local_mode', lambda: True)

    assert five_page.FivePageFirst(1, 0, 'job-1', job(), '5page').run() is True
    assert first_env['second_runs'] == 1
    assert first_env['firestore'] == []


# --- FivePageSecond: entrega no Drive -----------------------------------------

@pytest.fixture
def second(monkeypatch, tmp_path):
    state = {'trello': [], 'discord': [], 'convert_ok': True}

    class FakeConvert:
        def __init__(self, pdf_path):
            self.pdf_path = pdf_path

        def to_pptx(self):
            if not state['convert_ok']:
                return False
            pptx = self.pdf_path.with_suffix('.pptx')
            pptx.write_bytes(b'pptx')
            return pptx

    class FakeTrello:
        def __init__(self, card_id, list_target_name):
            state['trello'].append((card_id, list_target_name))

        def run(self):
            return True

    monkeypatch.setattr(five_page, 'get_url_fivepage', lambda folder: ('https://painel', 'Empresa Bonita'))
    monkeypatch.setattr(five_page, 'Convert', FakeConvert)
    monkeypatch.setattr(five_page, 'Trello', FakeTrello)
    monkeypatch.setattr(five_page, 'publish_message_discord', lambda data: state['discord'].append(data))
    monkeypatch.setattr(five_page, 'sleep', lambda seconds: None)
    monkeypatch.setattr(five_page, 'datetime', FixedDatetime)

    def build(**job_overrides):
        page = five_page.FivePageSecond(1, 0, 'job-1', job(**job_overrides), '5page')
        page.qvd_path = tmp_path / '_QVD'
        page.download_path.mkdir(parents=True, exist_ok=True)
        return page

    state['build'] = build
    return state


EXPECTED_STEM = '03.2026 - Empresa Bonita - Análise de Gestão e Risco'


def test_entrega_pdf_e_pptx_e_move_o_card(second, tmp_path):
    page = second['build']()
    (page.download_path / 'Relatorio.pdf').write_bytes(b'%PDF')

    assert page._FivePageSecond__move_to_drive() is True

    base = tmp_path / '_QVD' / 'EMPRESA_TESTE' / 'base'
    assert (base / f'{EXPECTED_STEM}.pdf').read_bytes() == b'%PDF'
    assert (base / f'{EXPECTED_STEM}.pptx').read_bytes() == b'pptx'
    assert second['trello'] == [('card-1', 'Qualidade: Produtos 6M')]
    assert second['discord'][-1]['status'] == 'success'


def test_conversao_da_adobe_falhando_entrega_so_o_pdf(second, tmp_path):
    second['convert_ok'] = False
    page = second['build']()
    (page.download_path / 'Relatorio.pdf').write_bytes(b'%PDF')

    assert page._FivePageSecond__move_to_drive() is True

    base = tmp_path / '_QVD' / 'EMPRESA_TESTE' / 'base'
    assert (base / f'{EXPECTED_STEM}.pdf').exists()
    assert not (base / f'{EXPECTED_STEM}.pptx').exists()


def test_sem_pdf_baixado_move_o_card_para_review(second):
    page = second['build']()

    assert page._FivePageSecond__move_to_drive() is False
    assert second['trello'] == [('card-1', 'Qualidade: Review')]
    assert second['discord'][-1]['status'] == 'error'


class FakeDriver:
    current_url = 'https://portal.suridata.com.br/login'

    def __init__(self):
        self.quit_called = False

    def quit(self):
        self.quit_called = True


def browser_steps(page, monkeypatch, failing_step=None):
    """Troca os passos do navegador por falsos; failing_step lança exceção."""
    driver = FakeDriver()
    calls = []

    def step(name):
        def run():
            calls.append(name)
            if name == '_FivePageSecond__init_browser':
                page.driver = driver
            if name == failing_step:
                raise RuntimeError(f'falhou em {name}')
        return run

    for name in ('_FivePageSecond__init_browser', '_FivePageSecond__login',
                 '_FivePageSecond__navigate_into_pages', '_FivePageSecond__download_pdf'):
        monkeypatch.setattr(page, name, step(name))
    return driver, calls


def test_falha_no_navegador_move_o_card_para_review_e_fecha_o_chrome(second, monkeypatch):
    page = second['build']()
    driver, _ = browser_steps(page, monkeypatch, failing_step='_FivePageSecond__download_pdf')

    with pytest.raises(RuntimeError):
        page.run()

    assert second['trello'] == [('card-1', 'Qualidade: Review')]
    assert driver.quit_called


def test_falha_ao_abrir_o_chrome_nao_quebra_ao_fechar(second, monkeypatch):
    page = second['build']()
    browser_steps(page, monkeypatch, failing_step='_FivePageSecond__init_browser')
    page.driver = None

    with pytest.raises(RuntimeError, match='init_browser'):
        page.run()

    assert second['trello'] == [('card-1', 'Qualidade: Review')]


def test_sucesso_fecha_o_chrome_e_entrega(second, monkeypatch):
    page = second['build']()
    driver, calls = browser_steps(page, monkeypatch)

    def fake_download():
        (page.download_path / 'Relatorio.pdf').write_bytes(b'%PDF')
    monkeypatch.setattr(page, '_FivePageSecond__download_pdf', fake_download)

    assert page.run() is True
    assert driver.quit_called
    assert second['trello'] == [('card-1', 'Qualidade: Produtos 6M')]


def test_iframe_que_nao_aparece_salva_print_e_explica_o_erro(second, monkeypatch):
    page = second['build']()
    page.driver = FakeDriver()
    saved = []
    monkeypatch.setattr(page, '_FivePageSecond__save_debug', lambda nome: saved.append(nome))

    class TimeoutWait:
        def __init__(self, driver, timeout, **kwargs):
            self.timeout = timeout

        def until(self, condition):
            raise five_page.TimeoutException()

    monkeypatch.setattr(five_page, 'WebDriverWait', TimeoutWait)

    with pytest.raises(RuntimeError, match='dashboard One Page não carregou'):
        page._FivePageSecond__download_pdf()

    assert saved == ['iframe_dashboard']


def test_pedido_sem_card_do_trello_nao_move_card(second):
    page = second['build'](trello_card_id=None)
    (page.download_path / 'Relatorio.pdf').write_bytes(b'%PDF')

    assert page._FivePageSecond__move_to_drive() is True
    assert second['trello'] == []
