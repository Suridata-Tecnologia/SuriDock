"""Sentinela: roda o processamento completo no Qlik e sobe a validação para o suri-storage.

O Qlik, o navegador, o Cloud Storage e o Trello são substituídos por dublês.
"""
from datetime import datetime

import pytest

from extensions import sentinel


class FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 11, 16, 10, 0, 0, tzinfo=tz)


CARD_PROCESSING = 'Operação: Processamento'
CARD_VALIDATION = 'Operação: Validação'
CARD_ERRORS = 'Operação: Erros'


def job(**overrides):
    data = {
        'company_name': 'EMPRESA_TESTE',
        'company_id': None,
        'discord_username': 'Trello - Card 1',
        'trello_card_id': 'card-1',
        'created_at': '16/11/2026 10:00:00',
        'type_proccess': 'sentinel',
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
        'trello': [],
        'discord': [],
        'edits': [],
        'navigations': [],
        'script_requests': [],
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
            return {'drive_folder': f'EMPRESA_{company_id}'}

    def fake_get_path(qvd_path, agent_number, sentinel=False):
        state['script_requests'].append((agent_number, sentinel))
        return tmp_path / 'script.qvs'

    def fake_navigate(driver, wait, agent_number, sentinel=False):
        state['navigations'].append((agent_number, sentinel))

    monkeypatch.setattr(sentinel, 'get_path_script_qvs', fake_get_path)
    monkeypatch.setattr(sentinel, 'edit_script_qvs', lambda **kwargs: state['edits'].append(kwargs))
    monkeypatch.setattr(sentinel, 'init_browser', lambda: state['driver'])
    monkeypatch.setattr(sentinel, 'navigate_to_process', fake_navigate)
    monkeypatch.setattr(sentinel, 'process_company', lambda driver: state['qlik_ok'])
    monkeypatch.setattr(sentinel, 'GoogleStorage', FakeGoogleStorage)
    monkeypatch.setattr(sentinel, 'Trello', FakeTrello)
    # lista atual do card no Trello: None = sem resposta do Trello (segue como antes);
    # uma lista = respostas em ordem; a última se repete
    state['card_lists'] = None
    def fake_card_list(card_id):
        lists = state['card_lists']
        if not lists:
            return None
        return lists.pop(0) if len(lists) > 1 else lists[0]
    monkeypatch.setattr(sentinel, 'get_card_list_name', fake_card_list)
    monkeypatch.setattr(sentinel, 'SuridataApi', FakeSuridataApi)
    monkeypatch.setattr(sentinel, 'publish_message_discord', lambda data: state['discord'].append(data))
    monkeypatch.setattr(sentinel, 'datetime', FixedDatetime)

    qvd_path = tmp_path / '_QVD'
    validation_dir = qvd_path / '_Analises' / 'Validação Automática'
    validation_dir.mkdir(parents=True)

    def build(**job_overrides):
        task = sentinel.Sentinel(2, 0, 'job-1', job(**job_overrides), 'Sentinela')
        task.qvd_path = qvd_path
        return task

    def add_validation(name, content='validacao'):
        path = validation_dir / name
        path.write_text(content, encoding='utf-8')
        return path

    state['build'] = build
    state['add_validation'] = add_validation
    state['validation_dir'] = validation_dir
    state['backup_dir'] = validation_dir / 'Backup'
    return state


def cards(env):
    return [name for _, name in env['trello']]


# --- fluxo completo ----------------------------------------------------------

def test_sucesso_sobe_a_validacao_com_a_data_e_guarda_backup(env):
    source = env['add_validation']('EMPRESA_TESTE.csv', 'dados da validação')

    assert env['build']().run() is True

    assert env['bucket'] == 'suri-storage'
    assert env['uploads'] == [
        ('EMPRESA_TESTE.csv', '2026-11-16_EMPRESA_TESTE.csv', 'text/csv', ('validação_qlik',))
    ]
    assert not source.exists()
    backup = env['backup_dir'] / '2026-11-16_EMPRESA_TESTE.csv'
    assert backup.read_text(encoding='utf-8') == 'dados da validação'
    assert cards(env) == [CARD_PROCESSING, CARD_VALIDATION]
    assert env['driver'].quit_calls == 1
    assert env['discord'][-1]['status'] == 'success'


def test_usa_o_script_e_o_app_da_sentinela(env):
    env['add_validation']('EMPRESA_TESTE.csv')

    env['build']().run()

    assert env['script_requests'] == [(2, True)]
    assert env['navigations'] == [(2, True)]
    assert env['edits'][0]['sentinel'] is True
    assert env['edits'][0]['company_name'] == 'EMPRESA_TESTE'


def test_busca_o_arquivo_sem_diferenciar_maiusculas(env):
    env['add_validation']('validacao_empresa_teste.csv')

    assert env['build']().run() is True
    assert env['uploads'][0][1] == '2026-11-16_validacao_empresa_teste.csv'


def test_backup_do_mesmo_dia_e_substituido(env):
    env['backup_dir'].mkdir()
    old_backup = env['backup_dir'] / '2026-11-16_EMPRESA_TESTE.csv'
    old_backup.write_text('versão da manhã', encoding='utf-8')
    env['add_validation']('EMPRESA_TESTE.csv', 'versão da tarde')

    assert env['build']().run() is True
    assert old_backup.read_text(encoding='utf-8') == 'versão da tarde'


def test_ignora_arquivos_que_nao_sao_csv(env):
    env['add_validation']('EMPRESA_TESTE.xlsx')

    assert env['build']().run() is False
    assert env['uploads'] == []


def test_nome_da_empresa_casa_por_trecho_e_pega_validacao_de_outra_empresa(env):
    """Documenta um risco: a busca é por trecho do nome, então a empresa 'AMIL'
    também pega o arquivo da 'VMP_AMIL'."""
    env['add_validation']('VMP_AMIL.csv')

    assert env['build'](company_name='AMIL').run() is True
    assert env['uploads'][0][0] == 'VMP_AMIL.csv'


# --- falhas ------------------------------------------------------------------

def test_sem_arquivo_de_validacao_avisa_erro(env):
    assert env['build']().run() is False

    assert env['uploads'] == []
    assert env['discord'][-1]['status'] == 'error'
    assert 'não encontrado' in env['discord'][-1]['stage']
    # o card já foi para "Validação" antes de procurar o arquivo
    assert cards(env) == [CARD_PROCESSING, CARD_VALIDATION]


def test_erro_no_qlik_move_o_card_para_erros(env):
    env['qlik_ok'] = False
    env['add_validation']('EMPRESA_TESTE.csv')

    assert env['build']().run() is False

    assert env['uploads'] == []
    assert cards(env) == [CARD_PROCESSING, CARD_ERRORS]
    assert env['discord'][-1]['stage'] == 'Erro no qlik'


def test_erro_no_qlik_nao_fecha_o_navegador(env):
    """Documenta o comportamento atual: quando o Qlik falha, a sentinela não chama
    driver.quit() (quem fecha o Chrome depois é o StartProcess)."""
    env['qlik_ok'] = False

    env['build']().run()

    assert env['driver'].quit_calls == 0


def test_falha_no_upload_propaga_o_erro_e_mantem_o_arquivo(env):
    env['upload_error'] = PermissionError('chave revogada')
    source = env['add_validation']('EMPRESA_TESTE.csv')

    with pytest.raises(PermissionError):
        env['build']().run()

    assert source.exists()


# --- Trello, cadastro e Discord ----------------------------------------------

def test_pedido_sem_card_nao_move_o_card(env):
    env['add_validation']('EMPRESA_TESTE.csv')

    assert env['build'](trello_card_id=None).run() is True
    assert env['trello'] == []


def test_company_id_substitui_o_nome_pela_pasta_da_api(env):
    task = env['build'](company_name='NOME_ANTIGO', company_id=55)

    assert task.mj['company_name'] == 'EMPRESA_55'


def test_mensagens_do_discord_vao_para_o_canal_sentinel(env):
    env['add_validation']('EMPRESA_TESTE.csv')

    env['build']().run()

    assert {message['discord_channel'] for message in env['discord']} == {'sentinel'}
    assert [message['progress'] for message in env['discord']] == [0, 20, 40, 60, 80, 100]


# --- card movido à mão (ex.: para "Operação: Finalizados") --------------------

def test_card_tirado_da_fila_nao_roda_nem_volta_para_processamento(env):
    env['card_lists'] = ['Operação: Finalizados']

    assert env['build']().run() is True

    assert env['trello'] == []
    assert env['edits'] == []
    assert env['navigations'] == []
    assert env['discord'][-1]['status'] == 'pending'
    assert 'Operação: Finalizados' in env['discord'][-1]['stage']


@pytest.mark.parametrize('lista', ['Operação: Aguardando Processamento', CARD_PROCESSING, CARD_ERRORS])
def test_card_nas_listas_da_fila_roda_normalmente(env, lista):
    env['add_validation']('EMPRESA_TESTE.csv')
    env['card_lists'] = [lista, CARD_PROCESSING]

    assert env['build']().run() is True

    assert cards(env) == [CARD_PROCESSING, CARD_VALIDATION]


def test_card_movido_durante_o_processamento_nao_vai_para_validacao(env):
    env['add_validation']('EMPRESA_TESTE.csv')
    env['card_lists'] = [CARD_PROCESSING, 'Operação: Finalizados']

    env['build']().run()

    assert cards(env) == [CARD_PROCESSING]


def test_card_movido_durante_o_processamento_nao_vai_para_erros(env):
    env['qlik_ok'] = False
    env['card_lists'] = [CARD_PROCESSING, 'Operação: Finalizados']

    assert env['build']().run() is False

    assert cards(env) == [CARD_PROCESSING]


def test_sem_resposta_do_trello_segue_como_antes(env):
    env['add_validation']('EMPRESA_TESTE.csv')
    env['card_lists'] = None

    assert env['build']().run() is True

    assert cards(env) == [CARD_PROCESSING, CARD_VALIDATION]


def test_pedido_sem_card_do_trello_nao_consulta_o_trello(env, monkeypatch):
    env['add_validation']('EMPRESA_TESTE.csv')
    monkeypatch.setattr(sentinel, 'get_card_list_name', lambda card_id: pytest.fail('não devia consultar o Trello'))

    assert env['build'](trello_card_id=None).run() is True
