"""Idioma da empresa: com mais de um cadastro na mesma pasta, vale o ativo."""
from extensions import database


class FakeCursor:
    def __init__(self, queries, rows):
        self.queries = queries
        self.rows = rows

    def execute(self, query):
        self.queries.append(query)

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, rows):
        self.queries = []
        self.rows = rows

    def cursor(self, dictionary=False):
        return FakeCursor(self.queries, self.rows)


def fake_db(rows):
    db = database.Database.__new__(database.Database)  # sem conectar no MySQL
    db.connection = FakeConnection(rows)
    return db


def test_idioma_ordena_cadastro_ativo_primeiro():
    db = fake_db([{'language_id': 2}, {'language_id': 1}])

    assert db.get_language_by_company('HELLMANN') is True
    assert f'ORDER BY {database.COMPANY_ACTIVE_FIRST}' in db.connection.queries[0]


def test_find_all_sem_ordem_nao_poe_order_by():
    db = fake_db([])
    db.find_all(table_name='companies', columns=['id'])
    assert 'ORDER BY' not in db.connection.queries[0]
