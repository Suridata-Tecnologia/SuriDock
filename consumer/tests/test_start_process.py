"""StartProcess.run: status no Firestore, Qlik, mensagens de erro e fechamento do Qlik."""
import pytest

import common
import start_process
from start_process import summarize_error


class FakeFirestore:
    jobs = {}
    sets = []

    def __init__(self, table):
        self.table = table

    def get_job(self, job_id):
        return FakeFirestore.jobs.get(job_id)

    def set_job(self, job_id, data, merge=True):
        FakeFirestore.sets.append((self.table, job_id, data))


class ForbiddenFirestore:
    def __init__(self, table):
        raise AssertionError('o modo local não deveria acessar o Firestore')


def make_app(result=True, error=None):
    class FakeApp:
        instances = []

        def __init__(self, agent_number, retry_count, job_id, data, pretty_name):
            FakeApp.instances.append((agent_number, retry_count, job_id, data['type_proccess'], pretty_name))

        def run(self):
            if error:
                raise error
            return result

    return FakeApp


def job(type_proccess='storage', status='queued'):
    return {
        'status': status,
        'type_proccess': type_proccess,
        'created_at': '16/11/2026 10:00:00',
        'company_name': 'EMPRESA_TESTE',
        'discord_username': 'Trello - Card 1',
    }


@pytest.fixture
def env(monkeypatch):
    FakeFirestore.jobs = {}
    FakeFirestore.sets = []
    state = {'qlik_ready': True, 'qlik_calls': [], 'discord': [], 'closed': []}

    def ensure_qlik_ready(agent_number):
        state['qlik_calls'].append(agent_number)
        return state['qlik_ready']

    monkeypatch.setattr(start_process, 'GoogleFirestore', FakeFirestore)
    monkeypatch.setattr(start_process, 'ensure_qlik_ready', ensure_qlik_ready)
    monkeypatch.setattr(start_process, 'publish_message_discord', lambda data: state['discord'].append(data))
    monkeypatch.setattr(start_process, 'close_process', lambda name: state['closed'].append(name))
    return state


def use_app(monkeypatch, class_name, app):
    monkeypatch.setattr(start_process, class_name, app)
    return app


def statuses(job_id):
    return [data['status'] for table, jid, data in FakeFirestore.sets if table == 'jobs' and jid == job_id]


def test_job_inexistente_e_ignorado(env, monkeypatch):
    app = use_app(monkeypatch, 'Storage', make_app())

    assert start_process.StartProcess(1, 0, 'job-x').run() is True
    assert app.instances == []
    assert FakeFirestore.sets == []


def test_job_cancelado_nao_roda(env, monkeypatch):
    FakeFirestore.jobs['job-1'] = job(status='cancelled')
    app = use_app(monkeypatch, 'Storage', make_app())

    assert start_process.StartProcess(1, 0, 'job-1').run() is True
    assert app.instances == []
    assert FakeFirestore.sets == []


def test_storage_com_sucesso_marca_running_e_completed(env, monkeypatch):
    FakeFirestore.jobs['job-1'] = job('storage')
    app = use_app(monkeypatch, 'Storage', make_app(result=True))

    assert start_process.StartProcess(2, 1, 'job-1').run() is True
    assert app.instances == [(2, 1, 'job-1', 'storage', 'Storage')]
    assert env['qlik_calls'] == [2]
    assert statuses('job-1') == ['running', 'completed']
    assert common.read_agent_states()[1] == 'agent2-stopped'


def test_storage_que_falha_marca_failed(env, monkeypatch):
    FakeFirestore.jobs['job-1'] = job('storage')
    use_app(monkeypatch, 'Storage', make_app(result=False))

    assert start_process.StartProcess(1, 0, 'job-1').run() is False
    assert statuses('job-1') == ['running', 'failed']


def test_qlik_indisponivel_avisa_no_discord_e_nao_roda_o_job(env, monkeypatch):
    FakeFirestore.jobs['job-1'] = job('storage')
    env['qlik_ready'] = False
    app = use_app(monkeypatch, 'Storage', make_app())

    assert start_process.StartProcess(1, 0, 'job-1').run() is False
    assert app.instances == []
    assert statuses('job-1') == ['running', 'failed']
    assert len(env['discord']) == 1
    message = env['discord'][0]
    assert message['status'] == 'error'
    assert message['stage'] == 'Erro: RuntimeError: O Qlik não ficou disponível (hub em localhost:4848 não respondeu)'
    assert message['discord_channel'] == 'bots'
    assert message['company'] == 'EMPRESA_TESTE'


def test_erro_na_sentinela_vai_para_o_canal_sentinel(env, monkeypatch):
    FakeFirestore.jobs['job-1'] = job('sentinel')
    use_app(monkeypatch, 'Sentinel', make_app(error=RuntimeError('falhou')))

    assert start_process.StartProcess(1, 0, 'job-1').run() is False
    assert env['discord'][0]['discord_channel'] == 'sentinel'


def test_primeira_fase_do_5page_nao_marca_completed(env, monkeypatch):
    FakeFirestore.jobs['job-1'] = job('fivepagefirst')
    use_app(monkeypatch, 'FivePageFirst', make_app(result=True))

    assert start_process.StartProcess(1, 0, 'job-1').run() is True
    assert statuses('job-1') == ['running']


def test_segunda_fase_do_5page_nao_usa_o_qlik(env, monkeypatch):
    FakeFirestore.jobs['job-1'] = job('fivepagesecond')
    use_app(monkeypatch, 'FivePageSecond', make_app(result=True))

    assert start_process.StartProcess(1, 0, 'job-1').run() is True
    assert env['qlik_calls'] == []
    assert env['closed'] == []
    assert statuses('job-1') == ['running', 'completed']


def test_fecha_qlik_e_chrome_quando_nenhum_outro_agente_esta_rodando(env, monkeypatch):
    FakeFirestore.jobs['job-1'] = job('storage')
    use_app(monkeypatch, 'Storage', make_app())

    start_process.StartProcess(1, 0, 'job-1').run()

    assert env['closed'] == ['chrome', 'qlik']


def test_mantem_o_qlik_aberto_se_outro_agente_esta_rodando(env, monkeypatch):
    FakeFirestore.jobs['job-1'] = job('storage')
    use_app(monkeypatch, 'Storage', make_app())
    common.set_agent_state(2, 'running')

    start_process.StartProcess(1, 0, 'job-1').run()

    assert env['closed'] == []
    assert common.read_agent_states()[1] == 'agent2-running'


def test_modo_local_nao_acessa_o_firestore(env, monkeypatch):
    monkeypatch.setattr(start_process, 'GoogleFirestore', ForbiddenFirestore)
    app = use_app(monkeypatch, 'Storage', make_app(result=True))

    assert start_process.StartProcess(1, 0, job_data=job('storage')).run() is True
    assert len(app.instances) == 1


def last_set(job_id):
    return [data for table, jid, data in FakeFirestore.sets if table == 'jobs' and jid == job_id][-1]


# --- motivo do erro no Discord e no Firestore ---------------------------------

def test_erro_mostra_o_motivo_no_discord(env, monkeypatch):
    FakeFirestore.jobs['job-1'] = job('fivepagefirst')
    use_app(monkeypatch, 'FivePageFirst', make_app(error=IndexError('list index out of range')))

    start_process.StartProcess(1, 0, 'job-1').run()

    assert env['discord'][0]['stage'] == 'Erro: IndexError: list index out of range'


def test_erro_grava_o_motivo_e_o_traceback_no_job(env, monkeypatch):
    FakeFirestore.jobs['job-1'] = job('storage')
    use_app(monkeypatch, 'Storage', make_app(error=PermissionError('chave revogada')))

    assert start_process.StartProcess(2, 3, 'job-1').run() is False

    data = last_set('job-1')
    assert data['status'] == 'failed'
    error = data['error']
    assert error['summary'] == 'PermissionError: chave revogada'
    assert 'Traceback' in error['traceback'] and 'PermissionError: chave revogada' in error['traceback']
    assert error['agent'] == 'produção 1 agent2'
    assert error['retry_count'] == 3
    assert error['at']


def test_erro_em_processo_sem_qlik_tambem_e_registrado(env, monkeypatch):
    FakeFirestore.jobs['job-1'] = job('fivepagesecond')
    use_app(monkeypatch, 'FivePageSecond', make_app(error=FileNotFoundError('pdf não encontrado')))

    assert start_process.StartProcess(1, 0, 'job-1').run() is False
    assert env['discord'][0]['stage'] == 'Erro: FileNotFoundError: pdf não encontrado'
    assert last_set('job-1')['error']['summary'] == 'FileNotFoundError: pdf não encontrado'


def test_erro_sem_dados_do_solicitante_nao_quebra_o_aviso(env, monkeypatch):
    data = job('fivepagesecond')
    del data['discord_username'], data['company_name']
    FakeFirestore.jobs['job-1'] = data
    use_app(monkeypatch, 'FivePageSecond', make_app(error=RuntimeError('falhou')))

    assert start_process.StartProcess(1, 0, 'job-1').run() is False
    assert env['discord'][0]['discord_username'] is None
    assert env['discord'][0]['company'] is None


def test_falha_sem_excecao_nao_grava_erro(env, monkeypatch):
    FakeFirestore.jobs['job-1'] = job('storage')
    use_app(monkeypatch, 'Storage', make_app(result=False))

    start_process.StartProcess(1, 0, 'job-1').run()

    assert 'error' not in last_set('job-1')
    assert env['discord'] == []


def test_traceback_guardado_e_cortado_no_final(env, monkeypatch):
    FakeFirestore.jobs['job-1'] = job('storage')
    use_app(monkeypatch, 'Storage', make_app(error=ValueError('x' * 5000 + ' FIM')))

    start_process.StartProcess(1, 0, 'job-1').run()

    traceback_text = last_set('job-1')['error']['traceback']
    assert len(traceback_text) == start_process.ERROR_TRACEBACK_LIMIT
    assert traceback_text.rstrip().endswith('FIM')


def test_modo_local_com_erro_nao_acessa_o_firestore(env, monkeypatch):
    monkeypatch.setattr(start_process, 'GoogleFirestore', ForbiddenFirestore)
    use_app(monkeypatch, 'Storage', make_app(error=RuntimeError('falhou')))

    assert start_process.StartProcess(1, 0, job_data=job('storage')).run() is False
    assert env['discord'][0]['stage'] == 'Erro: RuntimeError: falhou'


@pytest.mark.parametrize('error, expected', [
    (ValueError('script vazio'), 'ValueError: script vazio'),
    (RuntimeError(), 'RuntimeError'),
    # exceções do Selenium trazem o stacktrace do Chrome nas linhas seguintes
    (Exception('Message: no such element\nStacktrace:\n0x7ff6 <unknown>'), 'Exception: Message: no such element'),
    (Exception('\n\n  primeira linha útil  \nsegunda'), 'Exception: primeira linha útil'),
])
def test_summarize_error(error, expected):
    assert summarize_error(error) == expected


def test_summarize_error_corta_mensagens_longas():
    summary = summarize_error(ValueError('a' * 500))

    assert len(summary) == 200
    assert summary.endswith('...')
