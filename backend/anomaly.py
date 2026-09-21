import sqlite3

from backend.engine_support import get_table_columns, table_exists
from backend.sql_safety import quote_identifier, safe_table_name


class AnomalyDetector:
    def __init__(self, db_file):
        self.db_file = db_file
        self.conn = None

    def connect(self):
        self.conn = sqlite3.connect(self.db_file)

    def check_support(self, column, table_name="sales"):
        table_name = safe_table_name(table_name)
        if not table_exists(self.conn, table_name):
            return False, f"Table '{table_name}' does not exist."
        if column not in get_table_columns(self.conn, table_name):
            return False, f"Missing column: {column}"
        return True, None

    def detect_z_score(self, column, threshold=2.0, table_name="sales"):
        supported, _reason = self.check_support(column, table_name)
        if not supported:
            return []

        table_name = safe_table_name(table_name)
        query = (
            f'SELECT rowid, {quote_identifier(column)} FROM {quote_identifier(table_name)} '
            f'WHERE {quote_identifier(column)} IS NOT NULL'
        )
        cursor = self.conn.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()

        values = []
        numeric_rows = []
        for rowid, value in rows:
            try:
                numeric_value = float(value)
            except (TypeError, ValueError):
                continue
            values.append(numeric_value)
            # Keep the original (un-coerced) value for the output tuple,
            # exactly like the legacy implementation did -- only the
            # z-score math should ever see a float. This preserves int
            # columns (e.g. Sales) as ints in the result, not 9090.0.
            numeric_rows.append((rowid, value, numeric_value))

        if len(values) < 2:
            return []

        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        standard_deviation = variance ** 0.5

        if standard_deviation == 0:
            return []

        anomalies = []
        for rowid, original_value, numeric_value in numeric_rows:
            z_score = (numeric_value - mean) / standard_deviation
            if abs(z_score) >= threshold:
                anomalies.append((rowid, original_value, round(z_score, 2)))

        return anomalies
