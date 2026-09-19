import sqlite3
import pandas as pd

class DataSetManager:
    def __init__(self, db_file):
        self.db_file = db_file
        self.conn = None

    def connect(self):
        self.conn = sqlite3.connect(self.db_file)

    def create_tables(self, df):
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
            columns.append(f'"{column}" {sql_type}')

        columns_sql = ", ".join(columns)
        query = f"""CREATE TABLE IF NOT EXISTS sales(
            {columns_sql}
        )"""
        cursor.execute(query)
        self.conn.commit()

    def insert_data(self, df):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM sales")
        self.conn.commit()
        df.to_sql("sales", self.conn, if_exists="append", index=False)

    def get_data(self):
        return pd.read_sql_query("SELECT * FROM sales", self.conn)

    def get_table_info(self):
        cursor = self.conn.cursor()
        cursor.execute("PRAGMA table_info(sales)")
        return cursor.fetchall()
