import sqlite3

from backend.engine_support import get_table_columns, table_exists
from backend.sql_safety import quote_identifier, safe_table_name

# Every generic aggregation MetricsEngine can run. Kept as a single
# source of truth so get_grouped_metric() and the analytical-intelligence convenience
# wrappers (get_min/get_max/get_count/get_metric) never drift apart.
ALLOWED_AGGREGATIONS = ("SUM", "AVG", "MIN", "MAX", "COUNT")


class MetricsEngine:
    def __init__(self, db_file):
        self.db_file = db_file
        self.conn = None

    def connect(self):
        self.conn = sqlite3.connect(self.db_file)

    def get_sum(self, column, table_name="sales"):
        return self._aggregate("SUM", column, table_name)

    def get_average(self, column, table_name="sales"):
        return self._aggregate("AVG", column, table_name)

    def get_min(self, column, table_name="sales"):
        return self._aggregate("MIN", column, table_name)

    def get_max(self, column, table_name="sales"):
        return self._aggregate("MAX", column, table_name)

    def get_count(self, column, table_name="sales"):
        return self._aggregate("COUNT", column, table_name)

    def get_metric(self, aggregation, column, table_name="sales"):
        """Generic single-value aggregation for any of the supported
        aggregation kinds (SUM/AVG/MIN/MAX/COUNT). Dynamic measure,
        dynamic table -- no dependency on any particular column name."""
        aggregation = (aggregation or "").upper()
        if aggregation not in ALLOWED_AGGREGATIONS:
            raise ValueError("Unsupported aggregation")
        return self._aggregate(aggregation, column, table_name)

    def _aggregate(self, aggregation, column, table_name):
        table_name = safe_table_name(table_name)
        if not table_exists(self.conn, table_name):
            return None
        if column not in get_table_columns(self.conn, table_name):
            return None
        cursor = self.conn.cursor()
        cursor.execute(
            f'SELECT {aggregation}({quote_identifier(column)}) '
            f'FROM {quote_identifier(table_name)}'
        )
        return cursor.fetchone()[0]

    def get_grouped_metric(self, group_column, metric_column, aggregation, table_name="sales"):
        aggregation = (aggregation or "").upper()
        if aggregation not in ALLOWED_AGGREGATIONS:
            raise ValueError("Unsupported aggregation")

        table_name = safe_table_name(table_name)
        if not table_exists(self.conn, table_name):
            return []

        columns = get_table_columns(self.conn, table_name)
        if group_column not in columns or metric_column not in columns:
            return []

        query = f'''
            SELECT {quote_identifier(group_column)}, {aggregation}({quote_identifier(metric_column)})
            FROM {quote_identifier(table_name)}
            GROUP BY {quote_identifier(group_column)}
        '''
        cursor = self.conn.cursor()
        cursor.execute(query)
        return cursor.fetchall()

    def check_support(self, columns, table_name="sales"):
        """Return (supported, reason) without running any query -- lets a
        caller (e.g. the dashboard) explain *why* a metric is unavailable
        for the selected dataset before attempting it."""
        table_name = safe_table_name(table_name)
        if not table_exists(self.conn, table_name):
            return False, f"Table '{table_name}' does not exist."
        available = get_table_columns(self.conn, table_name)
        missing = [c for c in columns if c not in available]
        if missing:
            return False, f"Missing column(s): {', '.join(missing)}"
        return True, None
