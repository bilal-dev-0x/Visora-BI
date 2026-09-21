import sqlite3

import pandas as pd

from backend.sql_safety import quote_identifier, safe_table_name


class DataSetManager:
    """Legacy single-table dataset manager. Every method defaults to the
    original `sales` table name, so existing callers (app.py) keep working
    exactly as before. table_name is exposed as an optional parameter so
    the same class can also be pointed at a dynamic dataset table."""

    def __init__(self, db_file):
        self.db_file = db_file
        self.conn = None

    def connect(self):
        self.conn = sqlite3.connect(self.db_file)

    def create_tables(self, df, table_name="sales"):
        table_name = safe_table_name(table_name)
        cursor = self.conn.cursor()
        columns = []
        for column in df.columns:
            dtype = str(df[column].dtype)
            if "int" in dtype:
                sql_type = "INTEGER"
            elif "float" in dtype:
                sql_type = "REAL"
            else:
                sql_type = "TEXT"
            columns.append(f"{quote_identifier(column)} {sql_type}")

        columns_sql = ", ".join(columns)
        query = f"CREATE TABLE IF NOT EXISTS {quote_identifier(table_name)} ({columns_sql})"
        cursor.execute(query)
        self.conn.commit()

    def insert_data(self, df, table_name="sales"):
        table_name = safe_table_name(table_name)
        cursor = self.conn.cursor()
        cursor.execute(f"DELETE FROM {quote_identifier(table_name)}")
        self.conn.commit()
        df.to_sql(table_name, self.conn, if_exists="append", index=False)

    def get_data(self, table_name="sales"):
        table_name = safe_table_name(table_name)
        return pd.read_sql_query(f"SELECT * FROM {quote_identifier(table_name)}", self.conn)

    def get_table_info(self, table_name="sales"):
        table_name = safe_table_name(table_name)
        cursor = self.conn.cursor()
        cursor.execute(f"PRAGMA table_info({quote_identifier(table_name)})")
        return cursor.fetchall()
