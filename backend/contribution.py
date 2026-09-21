import sqlite3

from backend.engine_support import get_table_columns, table_exists
from backend.sql_safety import quote_identifier, safe_table_name


class ContributionAnalyzer:
    def __init__(self, db_file):
        self.db_file = db_file
        self.conn = None

    def connect(self):
        self.conn = sqlite3.connect(self.db_file)

    def check_support(self, dimension, metric, table_name="sales"):
        table_name = safe_table_name(table_name)
        if not table_exists(self.conn, table_name):
            return False, f"Table '{table_name}' does not exist."
        available = get_table_columns(self.conn, table_name)
        missing = [c for c in (dimension, metric) if c not in available]
        if missing:
            return False, f"Missing column(s): {', '.join(missing)}"
        return True, None

    def analyze(self, dimension, metric, table_name="sales"):
        supported, _reason = self.check_support(dimension, metric, table_name)
        if not supported:
            return []

        table_name = safe_table_name(table_name)
        total_query = f'SELECT SUM({quote_identifier(metric)}) FROM {quote_identifier(table_name)}'
        grouped_query = f'''
            SELECT {quote_identifier(dimension)}, SUM({quote_identifier(metric)}) AS metric_value
            FROM {quote_identifier(table_name)}
            GROUP BY {quote_identifier(dimension)}
            ORDER BY metric_value DESC
        '''

        cursor = self.conn.cursor()
        cursor.execute(total_query)
        total = cursor.fetchone()[0]

        if total is None or total == 0:
            return []

        cursor.execute(grouped_query)
        rows = cursor.fetchall()

        return [
            (
                dimension_value,
                metric_value,
                round((metric_value / total) * 100, 2)
            )
            for dimension_value, metric_value in rows
            if metric_value is not None
        ]
