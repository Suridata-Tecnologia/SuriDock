"""Storage: Qlik gera as bases, os CSVs sobem para o suri-storage e o Suripoint é acionado.

O Qlik, o navegador, o Cloud Storage, o Trello e o Suripoint são substituídos por dublês.
"""
import pytest
import requests

from extensions import storage


BASES = [
    'Base 10Maiores', 'Base Auditoria', 'Base Beneficiarios',
    'Base Highlights', 'Base Resumo', 'Base Utilização',
]
CARD_START = 'Operação: Atualizando no Portal (Storage)'
CARD_SUCCESS = 'Qualidade: Validação dados Portal 👀👀👀'
CARD_FAILURE = 'Operação: Ajustes e Correções Portal'


def make_response(status_code, text=''):
    # objeto real do requests: o bool() dele depende do status (ok = status < 400)
    response = requests.Response()
    response.status_code = status_code
    response._content = text.encode('utf-8')
    return response


def job(**overrides):
    data = {
        'company_name': 'EMPRESA_TESTE',
        'company_id': 10,
        'discord_user_id': None,
        'discord_username': 'Trello - Card 1',
        'trello_card_id': 'card-1',
        'narrative': False,
        'created_at': '16/11/2026 10:00:00',
        'type_proccess': 'storage',
    }
    data.update(overrides)
    return data


class FakeDriver:
    def __init__(self):
        self.quit_calls = 0

    def quit(self):
        self.quit_calls += 1


@pytest.fixture
def env(monkeypatch, tmp_path):
    state = {
        'qlik_ok': True,
        'upload_error': None,
        'uploads': [],
        'suripoint': make_response(200),
        'suripoint_calls': 0,
        'trello': [],
        'discord': [],
        'edits': [],
        'navigations': [],
        'api_calls': [],
        'driver': FakeDriver(),
    }

    class FakeGoogleStorage:
        def __init__(self, bucket):
            state['bucket'] = bucket

        def upload_file(self, filepath, new_filename, content_type, *prefix):
            if state['upload_error']:
                raise state['upload_error']
            state['uploads'].append((filepath.name, new_filename, content_type, prefix))

    class FakeTrello:
        def __init__(self, card_id, list_target_name):
            state['trello'].append((card_id, list_target_name))

        def run(self):
            return True

    class FakeSuridataApi:
        def get_company_by_id(self, company_id):
            state['api_calls'].append(company_id)
            return {'drive_folder': 'EMPRESA_DA_API'}

    def fake_post(url, timeout):
        state['suripoint_calls'] += 1
        state['suripoint_url'] = url
        if isinstance(state['suripoint'], Exception):
            raise state['suripoint']
        return state['suripoint']

    monkeypatch.setattr(storage, 'get_path_script_qvs', lambda qvd_path, agent_number: tmp_path / 'script.qvs')
    monkeypatch.setattr(storage, 'has_gestao_pos', lambda company: False)
    monkeypatch.setattr(storage, 'edit_script_qvs', lambda **kwargs: state['edits'].append(kwargs))
    monkeypatch.setattr(storage, 'init_browser', lambda download_path: state['driver'])
    monkeypatch.setattr(storage, 'navigate_to_process',
                        lambda driver, wait, agent_number: state['navigations'].append(agent_number))
    monkeypatch.setattr(storage, 'process_company', lambda driver: state['qlik_ok'])
    monkeypatch.setattr(storage, 'GoogleStorage', FakeGoogleStorage)
    monkeypatch.setattr(storage, 'Trello', FakeTrello)
    monkeypatch.setattr(storage, 'SuridataApi', FakeSuridataApi)
    monkeypatch.setattr(storage, 'publish_message_discord', lambda data: state['discord'].append(data))
    monkeypatch.setattr(storage, 'sleep', lambda seconds: None)
    monkeypatch.setattr(storage.requests, 'post', fake_post)

    qvd_path = tmp_path / '_QVD'

    def build(**job_overrides):
        task = storage.Storage(1, 0, 'job-1', job(**job_overrides), 'Storage')
        task.qvd_path = qvd_path
        return task

    def add_base_file(base, name):
        folder = qvd_path / '_Base Storage' / base
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / name
        path.write_text('coluna\nvalor\n', encoding='utf-8')
        return path

    state['build'] = build
    state['add_base_file'] = add_base_file
    state['qvd_path'] = qvd_path
    return state


def cards(env):
    return [name for _, name in env['trello']]


# --- fluxo completo ----------------------------------------------------------

def test_sucesso_sobe_as_seis_bases_e_aciona_o_suripoint(env):
    files = [env['add_base_file'](base, f'{base} - EMPRESA_TESTE.csv') for base in BASES]

    assert env['build']().run() is True

    assert env['bucket'] == 'suri-storage'
    assert sorted(prefix for *_, prefix in env['uploads']) == sorted(
        (f'Extração Produção/{base}',) for base in BASES
    )
    assert all(content_type == 'text/csv' for _, _, content_type, _ in env['uploads'])
    assert not any(path.exists() for path in files)
    assert env['suripoint_calls'] == 1
    assert env['suripoint_url'].endswith('/start')
    assert cards(env) == [CARD_START, CARD_SUCCESS]
    assert env['discord'][-1]['status'] == 'success'
    assert env['driver'].quit_calls == 1


def test_edita_o_script_com_a_atividade_portal(env):
    env['build']().run()

    assert env['edits'] == [{
        'script_path': env['edits'][0]['script_path'],
        'company_name': 'EMPRESA_TESTE',
        'activity': 'Portal',
        'language': 'Portugues',
        'month_analysis': 'não',
    }]
    assert env['navigations'] == [1]


def test_nao_sobe_arquivos_de_outras_empresas(env):
    other = env['add_base_file']('Base Resumo', 'Base Resumo - OUTRA_EMPRESA.csv')

    env['build']().run()

    assert env['uploads'] == []
    assert other.exists()


def test_sobe_apenas_um_arquivo_por_base(env):
    """Documenta o comportamento atual: o laço para no primeiro arquivo de cada base."""
    first = env['add_base_file']('Base Resumo', 'Base Resumo - EMPRESA_TESTE.csv')
    second = env['add_base_file']('Base Resumo', 'Base Resumo - EMPRESA_TESTE (1).csv')

    env['build']().run()

    assert len(env['uploads']) == 1
    assert [first.exists(), second.exists()].count(True) == 1


def test_nome_da_empresa_casa_por_trecho_e_pega_base_de_outra_empresa(env):
    """Documenta um risco: a busca é '*<empresa>*', então a empresa 'VMP' também pega
    o arquivo da 'VMP_AMIL' e sobe a base da empresa errada."""
    env['add_base_file']('Base Resumo', 'Base Resumo - VMP_AMIL.csv')

    env['build'](company_name='VMP').run()

    assert [name for name, *_ in env['uploads']] == ['Base Resumo - VMP_AMIL.csv']


def test_sem_nenhuma_base_ainda_aciona_o_suripoint(env):
    """Documenta o comportamento atual: sem arquivos para subir, o Storage não falha,
    aciona o Suripoint e marca sucesso."""
    assert env['build']().run() is True
    assert env['uploads'] == []
    assert env['suripoint_calls'] == 1


# --- falhas ------------------------------------------------------------------

def test_erro_no_qlik_nao_sobe_nada(env):
    env['qlik_ok'] = False
    env['add_base_file']('Base Resumo', 'Base Resumo - EMPRESA_TESTE.csv')

    assert env['build']().run() is False

    assert env['uploads'] == []
    assert env['suripoint_calls'] == 0
    assert env['driver'].quit_calls == 1
    assert cards(env) == [CARD_START, CARD_FAILURE]
    assert env['discord'][-1]['stage'] == 'erro no qlik'


def test_falha_no_upload_mantem_o_arquivo_e_nao_aciona_o_suripoint(env):
    env['upload_error'] = PermissionError('chave revogada')
    path = env['add_base_file']('Base Resumo', 'Base Resumo - EMPRESA_TESTE.csv')

    assert env['build']().run() is False

    assert path.exists()
    assert env['suripoint_calls'] == 0
    assert cards(env) == [CARD_START, CARD_FAILURE]
    assert env['discord'][-1]['stage'] == 'erro ao subir os arquivos para o storage'


@pytest.mark.parametrize('suripoint, expected', [
    (make_response(200), True),
    # 500 conta como sucesso: o Suripoint costuma processar mesmo devolvendo 500.
    # Usa um Response real, que é "falso" em Python quando o status é >= 400.
    (make_response(500, 'erro interno'), True),
    (make_response(404, 'não encontrado'), False),
    (requests.exceptions.ReadTimeout('demorou'), False),
])
def test_resposta_do_suripoint(env, suripoint, expected):
    env['suripoint'] = suripoint

    assert env['build']().run() is expected
    assert cards(env)[-1] == (CARD_SUCCESS if expected else CARD_FAILURE)


# --- Trello e cadastro --------------------------------------------------------

def test_primeira_fase_do_5page_nao_move_o_card(env):
    env['build'](type_proccess='fivepagefirst').run()

    assert env['trello'] == []


def test_pedido_sem_card_nao_move_o_card(env):
    env['build'](trello_card_id=None).run()

    assert env['trello'] == []


def test_sem_nome_da_pasta_busca_a_empresa_na_api(env):
    task = env['build'](company_name=None, company_id=77)

    assert env['api_calls'] == [77]
    assert task.mj['company_name'] == 'EMPRESA_DA_API'


def test_mensagens_do_discord_vao_para_o_canal_bots(env):
    env['build']().run()

    assert {message['discord_channel'] for message in env['discord']} == {'bots'}
    assert [message['progress'] for message in env['discord']] == [0, 15, 30, 45, 60, 75, 90, 100]
