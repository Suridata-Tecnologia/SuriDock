"""Cadastro da empresa no portal: com mais de um cadastro na mesma pasta do Drive
(ex.: um ativo e um inativo), as consultas devem trazer o ativo primeiro.

Caso real (chamado #8238): Hellmann tinha "Hellmann - Sulamerica" ativo e "Hellmann2"
inativo na mesma pasta; o 5Page abria o dashboard do inativo, com dados de 2024.
"""
import sqlite3

import pytest

import common
import database


class FakeCursor:
    def __init__(self, queries, rows):
        self.queries = queries
        self.rows = rows

    def execute(self, query):
        self.queries.append(query)

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, rows=None):
        self.queries = []
        self.rows = rows or []

    def cursor(self, dictionary=False):
        return FakeCursor(self.queries, self.rows)


def fake_db(rows=None):
    db = database.Database.__new__(database.Database)  # sem conectar no MySQL
    db.connection = FakeConnection(rows)
    return db


# --- a ordem em SQL de verdade ------------------------------------------------

def ordered_ids(rows):
    conn = sqlite3.connect(':memory:')
    conn.execute('CREATE TABLE companies (id INTEGER, status INTEGER, drive_path TEXT)')
    conn.executemany('INSERT INTO companies VALUES (?, ?, ?)', rows)
    query = f'SELECT id FROM companies ORDER BY {database.COMPANY_ACTIVE_FIRST}'
    return [row[0] for row in conn.execute(query)]


def test_cadastro_ativo_vem_antes_do_inativo_mesmo_com_id_menor():
    # status: 0 ativo, 1 inativo
    assert ordered_ids([(50, 1, 'HELLMANN'), (10, 0, 'HELLMANN')]) == [10, 50]


def test_inativo_fica_por_ultimo_e_implantacao_ou_historico_antes_dele():
    rows = [(1, 1, 'X'), (2, 3, 'X'), (3, 2, 'X'), (4, 0, 'X')]
    assert ordered_ids(rows) == [4, 3, 2, 1]


def test_status_vazio_conta_como_ativo():
    assert ordered_ids([(1, 1, 'X'), (2, None, 'X')]) == [2, 1]


def test_so_com_cadastro_inativo_ele_ainda_e_usado():
    assert ordered_ids([(7, 1, 'X')]) == [7]


# --- as consultas usam a ordem ------------------------------------------------

@pytest.mark.parametrize('method', ['find_pretty_name_and_operator_name', 'find_pretty_name_and_policy'])
def test_consultas_da_empresa_ordenam_ativo_primeiro(method):
    db = fake_db()
    getattr(db, method)('HELLMANN')

    query = db.connection.queries[0]
    assert 'companies.drive_path = "HELLMANN"' in query
    assert f'ORDER BY {database.COMPANY_ACTIVE_FIRST}' in query


def test_find_all_sem_ordem_nao_poe_order_by():
    db = fake_db()
    db.find_all(table_name='companies', columns=['id'])
    assert 'ORDER BY' not in db.connection.queries[0]


def test_has_gestao_pos_ordena_ativo_primeiro(monkeypatch):
    db = fake_db([{'suridata_product': 'Gestão Pós'}])
    monkeypatch.setattr(common, 'Database', lambda: db)

    assert common.has_gestao_pos('HELLMANN') is True
    assert f'ORDER BY {database.COMPANY_ACTIVE_FIRST}' in db.connection.queries[0]


def test_url_do_5page_usa_o_primeiro_cadastro_e_avisa_quando_ha_mais_de_um(monkeypatch):
    rows = [
        {'dashboard_param': 'Hellmann - Sulamerica', 'id': 10, 'status': 0},
        {'dashboard_param': 'Hellmann2', 'id': 50, 'status': 1},
    ]

    class FakeDatabase:
        def find_pretty_name_and_operator_name(self, drive_folder):
            return rows

    monkeypatch.setattr(common, 'Database', FakeDatabase)
    warnings = []
    monkeypatch.setattr(common.logger, 'warning', lambda message: warnings.append(message))

    url, pretty_name = common.get_url_fivepage('HELLMANN')

    assert pretty_name == 'Hellmann - Sulamerica'
    assert '/dashboard/MTA=/' in url  # 'MTA=' = '10'
    assert len(warnings) == 1
    assert 'Hellmann2' in warnings[0]
