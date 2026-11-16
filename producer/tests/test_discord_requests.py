"""Pedidos feitos pelos comandos do Discord (/5page, /relatorioppt, /storage).

Cada empresa encontrada em _QVD vira um job na fila; a resposta ao usuário depende
de quantas empresas foram pedidas e encontradas.
"""
import pytest

from extensions import five_page, relatorio_ppt, storage


MODULES = [five_page, relatorio_ppt, storage]


@pytest.fixture
def found(monkeypatch):
    """Lista de empresas que o CheckCompanies 'encontra' em _QVD."""
    state = {'companies': None}

    class FakeCheckCompanies:
        def __init__(self, companies):
            self.companies = companies

        def run(self):
            if state['companies'] is None:
                return self.companies
            return [c for c in self.companies if c in state['companies']]

    for module in MODULES:
        monkeypatch.setattr(module, 'CheckCompanies', FakeCheckCompanies)
    monkeypatch.setattr(five_page, 'get_formated_time_now', lambda: '16/11/2026 10:00:00')
    monkeypatch.setattr(relatorio_ppt, 'get_formated_time_now', lambda: '16/11/2026 10:00:00')
    monkeypatch.setattr(storage, 'get_formated_time_now', lambda: '16/11/2026 10:00:00')
    return state


def make_request(kind, companies, **kwargs):
    if kind == 'fivepage':
        return five_page.FivePage(42, 900, companies, kwargs.get('dark_mode', False))
    if kind == 'relatorioppt':
        return relatorio_ppt.RelatorioPPT(42, 900, companies, kwargs.get('english', False),
                                          kwargs.get('month_analysis', 'não'), kwargs.get('audith', False))
    return storage.Storage(42, 900, companies)


EXPECTED_TYPE = {'fivepage': 'fivepagefirst', 'relatorioppt': 'relatorioppt', 'storage': 'storage'}


@pytest.mark.parametrize('kind', ['fivepage', 'relatorioppt', 'storage'])
def test_cada_empresa_encontrada_vira_um_job(found, produced, kind):
    make_request(kind, 'empresa_a, empresa_b').run()

    assert [job['company_name'] for job in produced] == ['EMPRESA_A', 'EMPRESA_B']
    for job in produced:
        assert job['status'] == 'queued'
        assert job['type_proccess'] == EXPECTED_TYPE[kind]
        assert job['created_at'] == '16/11/2026 10:00:00'
        assert job['discord_user_id'] == 42
        assert job['discord_message_id'] == 900
        assert job['discord_username'] == '<@42>'
        assert job['trello_card_id'] is None
        assert job['company_id'] is None
        assert job['job_id'] is None  # o Producer gera um uuid


@pytest.mark.parametrize('kind', ['fivepage', 'relatorioppt', 'storage'])
def test_empresa_nao_encontrada_nao_vai_para_a_fila(found, produced, kind):
    found['companies'] = []

    answer = make_request(kind, 'empresa_x').run()

    assert produced == []
    assert answer.startswith('não encontrei a empresa EMPRESA_X')


@pytest.mark.parametrize('kind', ['fivepage', 'relatorioppt', 'storage'])
def test_varias_empresas_nao_encontradas(found, produced, kind):
    found['companies'] = []

    answer = make_request(kind, 'empresa_x, empresa_y').run()

    assert answer == 'as empresas a seguir não foram encontradas na pasta _QVD: EMPRESA_X, EMPRESA_Y'


@pytest.mark.parametrize('kind', ['fivepage', 'relatorioppt', 'storage'])
def test_resposta_lista_empresas_que_nao_foram_encontradas(found, produced, kind):
    """Documenta o comportamento atual: se só parte das empresas existe em _QVD, a
    resposta diz que todas foram para a fila, inclusive as que não foram."""
    found['companies'] = ['EMPRESA_A']

    answer = make_request(kind, 'empresa_a, empresa_x').run()

    assert [job['company_name'] for job in produced] == ['EMPRESA_A']
    assert answer == 'as empresas a seguir foram adicionadas na fila: EMPRESA_A, EMPRESA_X'


def test_5page_leva_a_opcao_de_capa_escura(found, produced):
    answer = make_request('fivepage', 'empresa_a', dark_mode=True).run()

    assert produced[0]['dark_mode'] is True
    assert 'capa escura' in answer


def test_5page_capa_clara_por_padrao(found, produced):
    answer = make_request('fivepage', 'empresa_a').run()

    assert produced[0]['dark_mode'] is False
    assert 'capa clara' in answer


@pytest.mark.parametrize('english, idioma', [(True, 'inglês'), (False, 'português')])
def test_relatorio_leva_idioma_periodo_e_auditoria(found, produced, english, idioma):
    answer = make_request('relatorioppt', 'empresa_a', english=english,
                          month_analysis='3 meses', audith=True).run()

    job = produced[0]
    assert job['narrative'] is english
    assert job['month_analysis'] == '3 meses'
    assert job['audith'] is True
    assert answer == f'sua solicitação para gerar o relatório em {idioma} da empresa EMPRESA_A foi adicionada na fila'


def test_storage_resposta_para_uma_empresa(found, produced):
    assert make_request('storage', 'empresa_a').run() == \
        'sua solicitação para gerar o storage da empresa EMPRESA_A foi adicionada na fila'
