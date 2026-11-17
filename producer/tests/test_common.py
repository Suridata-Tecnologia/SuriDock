"""common.py: empresas digitadas no Discord, pastas do Drive e envio do job (Firestore + RabbitMQ)."""
import json
import re

import pytest

import common


# --- SplitCompanies -------------------------------------------------------------

def test_split_companies_separa_por_virgula_e_deixa_em_maiusculas():
    assert common.SplitCompanies(' empresa_a,Empresa_B ,  empresa_c').run() == [
        'EMPRESA_A', 'EMPRESA_B', 'EMPRESA_C'
    ]


def test_split_companies_com_uma_empresa():
    assert common.SplitCompanies('vmp_amil').run() == ['VMP_AMIL']


def test_split_companies_mantem_itens_vazios():
    """Documenta o comportamento atual: vírgula sobrando vira um item vazio
    (depois o CheckCompanies descarta, porque não existe pasta com nome vazio)."""
    assert common.SplitCompanies('EMPRESA_A,').run() == ['EMPRESA_A', '']


# --- DriveAPI -------------------------------------------------------------------

class FakeDrive:
    def __init__(self, pages):
        self.pages = list(pages)
        self.requests = []

    def files(self):
        return self

    def list(self, **kwargs):
        self.requests.append(kwargs)
        return self

    def execute(self):
        return self.pages.pop(0)


@pytest.fixture
def drive(monkeypatch):
    state = {'drive': FakeDrive([{'files': []}]), 'creds_error': None}

    def from_service_account_file(path, scopes):
        state['creds_path'] = path
        if state['creds_error']:
            raise state['creds_error']
        return 'credenciais'

    monkeypatch.setattr(common.Credentials, 'from_service_account_file', from_service_account_file)
    monkeypatch.setattr(common, 'build', lambda service, version, credentials: state['drive'])
    return state


def test_drive_api_percorre_todas_as_paginas(drive):
    drive['drive'] = FakeDrive([
        {'files': [{'id': '1', 'name': 'EMPRESA_A'}], 'nextPageToken': 'p2'},
        {'files': [{'id': '2', 'name': 'EMPRESA_B'}]},
    ])

    assert common.DriveAPI('pasta-qvd').get_folders_drive_by_id() == ['EMPRESA_A', 'EMPRESA_B']
    assert [r['pageToken'] for r in drive['drive'].requests] == [None, 'p2']
    assert "'pasta-qvd' in parents" in drive['drive'].requests[0]['q']
    assert drive['creds_path'] == './credentials/suridata-drive-access.json'


def test_drive_api_pode_devolver_id_e_nome(drive):
    drive['drive'] = FakeDrive([{'files': [{'id': '1', 'name': 'EMPRESA_A'}]}])

    assert common.DriveAPI('pasta').get_folders_drive_by_id(onlyFolder=False) == [{'id': '1', 'name': 'EMPRESA_A'}]


def test_drive_api_sem_credencial_devolve_lista_vazia(drive):
    drive['creds_error'] = FileNotFoundError('credentials/suridata-drive-access.json')

    assert common.DriveAPI('pasta').get_folders_drive_by_id() == []


# --- CheckCompanies -------------------------------------------------------------

@pytest.fixture
def folders(monkeypatch):
    state = {'folders': [], 'parents': []}

    class FakeDriveAPI:
        def __init__(self, parent_id):
            state['parents'].append(parent_id)

        def get_folders_drive_by_id(self):
            return state['folders']

    monkeypatch.setattr(common, 'DriveAPI', FakeDriveAPI)
    return state


def test_check_companies_mantem_so_as_que_tem_pasta_em_qvd(folders):
    folders['folders'] = ['EMPRESA_A', 'EMPRESA_C']

    assert common.CheckCompanies(['EMPRESA_A', 'EMPRESA_B', 'EMPRESA_C']).run() == ['EMPRESA_A', 'EMPRESA_C']
    assert folders['parents'] == ['drive-qvd-teste']


def test_check_companies_compara_em_maiusculas(folders):
    folders['folders'] = ['EMPRESA_A']

    assert common.CheckCompanies(['empresa_a']).run() == ['empresa_a']


def test_check_companies_nao_acha_pasta_com_minusculas_no_drive(folders):
    """Documenta o comportamento atual: o nome digitado vira maiúsculo, mas o nome da
    pasta no Drive não; uma pasta 'Empresa_A' nunca é encontrada."""
    folders['folders'] = ['Empresa_A']

    assert common.CheckCompanies(['EMPRESA_A']).run() == []


def test_check_companies_sem_acesso_ao_drive_descarta_todas(folders):
    folders['folders'] = []

    assert common.CheckCompanies(['EMPRESA_A']).run() == []


# --- Producer -------------------------------------------------------------------

class FakeChannel:
    def __init__(self):
        self.declared = []
        self.published = []

    def queue_declare(self, queue, durable):
        self.declared.append((queue, durable))

    def basic_publish(self, exchange, routing_key, body):
        self.published.append((exchange, routing_key, body))


class FakeConnection:
    def __init__(self, params):
        self.params = params
        self.channel_obj = FakeChannel()
        self.closed = False

    def channel(self):
        return self.channel_obj

    def close(self):
        self.closed = True


@pytest.fixture
def rabbit(monkeypatch, firestore):
    state = {'connections': []}

    def connect(params):
        connection = FakeConnection(params)
        state['connections'].append(connection)
        return connection

    monkeypatch.setattr(common.pika, 'BlockingConnection', connect)
    monkeypatch.setattr(common, 'GoogleFirestore', firestore)
    return state


def test_producer_grava_o_job_e_publica_so_o_id_na_fila(rabbit, firestore):
    data = {'status': 'queued', 'type_proccess': 'storage', 'company_name': 'EMPRESA_A'}

    common.Producer(data, job_id='job-1').run()

    assert firestore.sets == [('jobs', 'job-1', data)]
    connection = rabbit['connections'][0]
    assert connection.channel_obj.declared == [('suridata_queue_teste', True)]
    exchange, queue, body = connection.channel_obj.published[0]
    assert (exchange, queue) == ('', 'suridata_queue_teste')
    assert json.loads(body) == {'job_id': 'job-1'}
    assert connection.closed


def test_producer_conecta_no_host_e_porta_do_rabbitmq(rabbit):
    common.Producer({'status': 'queued'}, job_id='job-1').run()

    params = rabbit['connections'][0].params
    assert params.host == 'rabbitmq.invalid'
    assert params.port == 5672
    assert params.credentials.username == 'teste'


def test_producer_gera_um_id_quando_nao_recebe(rabbit, firestore):
    common.Producer({'status': 'queued'}).run()
    common.Producer({'status': 'queued'}).run()

    ids = [job_id for _, job_id, _ in firestore.sets]
    assert len(set(ids)) == 2
    assert all(re.fullmatch(r'[0-9a-f-]{36}', job_id) for job_id in ids)


def test_producer_grava_no_firestore_antes_de_publicar(rabbit, firestore, monkeypatch):
    """Se o Firestore falhar, nada vai para a fila (o consumer ignoraria um id sem job)."""
    class BrokenFirestore:
        def __init__(self, table):
            pass

        def set_job(self, job_id, data):
            raise PermissionError('chave revogada')

    monkeypatch.setattr(common, 'GoogleFirestore', BrokenFirestore)

    with pytest.raises(PermissionError):
        common.Producer({'status': 'queued'}, job_id='job-1').run()
    assert rabbit['connections'] == []


def test_get_formated_time_now_no_formato_do_footer():
    assert re.fullmatch(r'\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}', common.get_formated_time_now())
