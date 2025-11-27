from dotenv         import load_dotenv

import mysql.connector
import os



load_dotenv()
SURIDB_HOST     = os.getenv('SURIDB_HOST')
SURIDB_USERNAME = os.getenv('SURIDB_USERNAME')
SURIDB_PASSWORD = os.getenv('SURIDB_PASSWORD')
SURIDB_DATABASE = os.getenv('SURIDB_DATABASE')
SURIDB_PORT     = os.getenv('SURIDB_PORT')



class Database():
    def __init__(self):
        self.connection = mysql.connector.connect(
            host     = SURIDB_HOST,
            user     = SURIDB_USERNAME,
            password = SURIDB_PASSWORD,
            database = SURIDB_DATABASE,
            port     = SURIDB_PORT
        )

    
    def find_all(self, table_name, condition=None, columns=[], related_table=None, left_on='id', right_on='id'):
        if not isinstance(columns, list):
            raise Exception('Columns precisa ser uma lista de colunas.')

        cursor = self.connection.cursor(dictionary=True)

        query = f'''
            SELECT {', '.join(columns) if columns else '*'}
            FROM {table_name}
            {f'JOIN {related_table} ON {table_name}.{left_on} = {related_table}.{right_on}' if related_table else ''}
            {f"WHERE {condition}" if condition else ''}
        '''
        
        cursor.execute(query)
        return cursor.fetchall()