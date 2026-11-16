"""StartProcess.run: status no Firestore, Qlik, mensagens de erro e fechamento do Qlik."""
import pytest

import common
import start_process


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
    assert message['stage'] == 'Ocorreu um erro desconhecido'
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
