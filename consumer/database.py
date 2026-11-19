from dotenv         import load_dotenv

import mysql.connector
import os



load_dotenv()
SURIDB_HOST     = os.getenv('SURIDB_HOST')
SURIDB_USERNAME = os.getenv('SURIDB_USERNAME')
SURIDB_PASSWORD = os.getenv('SURIDB_PASSWORD')
SURIDB_DATABASE = os.getenv('SURIDB_DATABASE')
SURIDB_PORT     = os.getenv('SURIDB_PORT')

# companies.status: 0 = Ativo, 1 = Inativo, 2 = Implantação, 3 = Histórico.
# Uma mesma pasta do Drive pode ter mais de um cadastro (ex.: um ativo e um inativo).
# Esta ordem põe o ativo primeiro e o inativo por último; o [0] das consultas passa a ser
# o cadastro certo. Se só houver o inativo, ele ainda é usado, como antes.
COMPANY_ACTIVE_FIRST = (
    'COALESCE(companies.status, 0) = 1, '
    'COALESCE(companies.status, 0) <> 0, '
    'companies.id DESC'
)



class Database():
    def __init__(self):
        self.connection = mysql.connector.connect(
            host     = SURIDB_HOST,
            user     = SURIDB_USERNAME,
            password = SURIDB_PASSWORD,
            database = SURIDB_DATABASE,
            port     = SURIDB_PORT
        )


    def find_pretty_name_and_policy(self, drive_folder):
        data = self.find_all(
            table_name='companies',
            left_on='operator_id',
            condition=f'companies.drive_path = "{drive_folder}"',
            columns=['companies.dashboard_param', 'companies.policy', 'companies.audit_date', 'companies.suridata_product'],
            order_by=COMPANY_ACTIVE_FIRST
        )

        return data
    

    def find_pretty_name_and_operator_name(self, drive_folder):
        data = self.find_all(
            table_name='companies',
            left_on='operator_id',
            condition=f'companies.drive_path = "{drive_folder}"',
            columns=['companies.pretty_name', 'companies.dashboard_param', 'operators.nickname', 'companies.id', 'companies.status'],
            related_table='operators',
            order_by=COMPANY_ACTIVE_FIRST
        )

        return data
    
    
    def find_all(self, table_name, condition=None, columns=[], related_table=None, left_on='id', right_on='id', order_by=None):
        if not isinstance(columns, list):
            raise Exception('Columns precisa ser uma lista de colunas.')

        cursor = self.connection.cursor(dictionary=True)

        query = f'''
            SELECT {', '.join(columns) if columns else '*'}
            FROM {table_name}
            {f'JOIN {related_table} ON {table_name}.{left_on} = {related_table}.{right_on}' if related_table else ''}
            {f"WHERE {condition}" if condition else ''}
            {f"ORDER BY {order_by}" if order_by else ''}
        '''
        
        cursor.execute(query)
        return cursor.fetchall()