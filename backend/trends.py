import sqlite3

from backend.engine_support import get_table_columns, table_exists
from backend.sql_safety import quote_identifier, safe_table_name

REQUIRED_COLUMNS = ("Order Date", "Sales")
OPTIONAL_COLUMNS = ("Profit",)


class TrendEngine:
    def __init__(self, db_file):
        self.db_file = db_file
        self.conn = None

    def connect(self):
        self.conn = sqlite3.connect(self.db_file)

    def check_support(self, table_name="sales"):
        """Return (supported, reason) for trend analysis on table_name."""
        table_name = safe_table_name(table_name)
        if not table_exists(self.conn, table_name):
            return False, f"Table '{table_name}' does not exist."
        available = get_table_columns(self.conn, table_name)
        missing = [c for c in REQUIRED_COLUMNS if c not in available]
        if missing:
            return False, f"Missing required column(s) for trend analysis: {', '.join(missing)}"
        return True, None

    def get_monthly_metrics(self, table_name="sales"):
        """Preserves the original algorithm exactly for tables that have
        the required business fields. Returns [] (not a crash) when the
        selected dataset's schema doesn't support trend analysis."""
        supported, _reason = self.check_support(table_name)
        if not supported:
            return []

        table_name = safe_table_name(table_name)
        columns = get_table_columns(self.conn, table_name)
        profit_select = (
            f"SUM({quote_identifier('Profit')})"
            if "Profit" in columns
            else "NULL"
        )

        query = f'''
            SELECT
                strftime('%Y-%m', {quote_identifier("Order Date")}) AS month,
                SUM({quote_identifier("Sales")}) AS total_sales,
                {profit_select} AS total_profit
            FROM {quote_identifier(table_name)}
            GROUP BY month
            ORDER BY month
        '''
        cursor = self.conn.cursor()
        cursor.execute(query)
        return cursor.fetchall()

    def calculate_growth(self, monthly_data):
        growth_data = []
        previous_sales = None
        for month, sales, profit in monthly_data:
            if previous_sales is None or not sales or not previous_sales:
                growth = None
            else:
                growth = round(((sales - previous_sales) / previous_sales) * 100, 2)
            growth_data.append((month, sales, profit, growth))
            previous_sales = sales
        return growth_data

    def calculate_moving_average(self, monthly_data, window=3):
        moving_data = []
        sales_window = []
        for month, sales, profit in monthly_data:
            sales_window.append(sales)
            if len(sales_window) < window:
                moving_average = None
            else:
                moving_average = round(sum(sales_window) / window, 2)
                sales_window.pop(0)
            moving_data.append((month, sales, moving_average))
        return moving_data
