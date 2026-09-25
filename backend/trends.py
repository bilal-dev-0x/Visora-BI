import sqlite3

from backend.engine_support import get_table_columns, table_exists
from backend.sql_safety import quote_identifier, safe_table_name

REQUIRED_COLUMNS = ("Order Date", "Sales")
OPTIONAL_COLUMNS = ("Profit",)

# Default window for the generic moving-average calculation. Kept as a
# module constant (not hardcoded inline) so behavior stays deterministic
# and easy to reason about/override per call.
DEFAULT_MOVING_AVERAGE_WINDOW = 3


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

    # -- Generic (arbitrary date column + arbitrary numeric
    # measure) trend analysis. These never assume "Order Date" or
    # "Sales" -- callers (typically backend/capabilities.py's detected
    # date_column/measure_column pair) supply the columns explicitly.
    # The legacy methods above are untouched and keep their exact
    # original behavior/return shapes for existing callers.

    def check_support_generic(self, date_column, measure_column, table_name="sales"):
        """Return (supported, reason) for trend analysis using an
        arbitrary date column + numeric measure column pair."""
        table_name = safe_table_name(table_name)
        if not table_exists(self.conn, table_name):
            return False, f"Table '{table_name}' does not exist."
        available = get_table_columns(self.conn, table_name)
        missing = [c for c in (date_column, measure_column) if c not in available]
        if missing:
            return False, f"Missing column(s) for trend analysis: {', '.join(missing)}"
        return True, None

    def get_monthly_metrics_generic(self, date_column, measure_column, table_name="sales"):
        """Monthly SUM(measure_column) grouped by strftime('%Y-%m', date_column).
        Returns a list of (period, value) tuples, ordered chronologically.
        Returns [] (never raises) when the pair isn't supported on this
        table, or when the date column doesn't parse into any period."""
        supported, _reason = self.check_support_generic(date_column, measure_column, table_name)
        if not supported:
            return []

        table_name = safe_table_name(table_name)
        query = f'''
            SELECT
                strftime('%Y-%m', {quote_identifier(date_column)}) AS period,
                SUM({quote_identifier(measure_column)}) AS total_value
            FROM {quote_identifier(table_name)}
            WHERE {quote_identifier(date_column)} IS NOT NULL
            GROUP BY period
            HAVING period IS NOT NULL
            ORDER BY period
        '''
        cursor = self.conn.cursor()
        cursor.execute(query)
        return cursor.fetchall()

    @staticmethod
    def _period_gap_months(previous_period, period):
        """Best-effort "how many months apart" between two 'YYYY-MM'
        period labels. Returns None (never raises) if either period
        isn't in that format -- a missing/odd label should never crash
        growth calculation, it just loses the gap annotation."""
        if not previous_period or not period:
            return None
        try:
            prev_year, prev_month = (int(part) for part in previous_period.split("-"))
            year, month = (int(part) for part in period.split("-"))
        except (ValueError, AttributeError):
            return None
        return (year - prev_year) * 12 + (month - prev_month)

    def calculate_growth_generic(self, monthly_data):
        """Period-over-period growth % for arbitrary (period, value)
        pairs. Never divides by zero and never emits NaN/Infinity:
        every entry has an explicit growth_reason instead when growth
        can't be meaningfully computed (no previous period, a zero
        baseline, a missing value, or the previous period isn't
        actually adjacent -- a gap of more than one period)."""
        growth_data = []
        previous_value = None
        previous_period = None
        for period, value in monthly_data:
            gap = self._period_gap_months(previous_period, period)
            if previous_period is None:
                growth_percent, reason = None, "no_previous_period"
            elif value is None or previous_value is None:
                growth_percent, reason = None, "missing_value"
            elif previous_value == 0:
                growth_percent, reason = None, "zero_baseline"
            elif gap is not None and gap != 1:
                # Periods exist but aren't consecutive months -- don't
                # silently imply a monthly rate across a gap.
                growth_percent, reason = None, "non_adjacent_period"
            else:
                growth_percent = round(((value - previous_value) / previous_value) * 100, 2)
                reason = None
            growth_data.append({
                "period": period,
                "value": value,
                "growth_percent": growth_percent,
                "growth_reason": reason,
                "period_gap_months": gap,
            })
            previous_value = value
            previous_period = period
        return growth_data

    def calculate_moving_average_generic(self, monthly_data, window=DEFAULT_MOVING_AVERAGE_WINDOW):
        """Deterministic moving average over arbitrary (period, value)
        pairs. Safe when fewer observations exist than the requested
        window (returns None with an explicit reason, "insufficient_
        periods", rather than a partial/misleading average). Also safe
        against a missing (None) value landing inside the window: a
        window that contains a missing value never silently falls back
        to averaging only the observed values in it -- that would be
        indistinguishable from a real full-window average once
        rounded, which is exactly the kind of quiet, misleading
        fabrication the analytical context must not produce. Instead
        it reports None with reason "missing_value_in_window", the
        same explicit-reason pattern calculate_growth_generic() uses.
        """
        if window < 1:
            window = 1

        moving_data = []
        value_window = []
        for period, value in monthly_data:
            value_window.append(value)
            if len(value_window) < window:
                moving_average, reason = None, "insufficient_periods"
            elif any(item is None for item in value_window):
                moving_average, reason = None, "missing_value_in_window"
            else:
                moving_average, reason = round(sum(value_window) / window, 2), None

            if len(value_window) >= window:
                value_window.pop(0)

            moving_data.append({
                "period": period,
                "value": value,
                "moving_average": moving_average,
                "moving_average_reason": reason,
            })
        return moving_data

    def compare_last_two_periods_generic(self, monthly_data):
        """A single, deterministic comparison between the two most
        recent observed periods -- no speculative business
        interpretation, just the numbers and, where relevant, why a
        percentage isn't meaningful (zero baseline, missing value)."""
        if len(monthly_data) < 2:
            return {
                "available": False,
                "reason": "Fewer than two periods are available for comparison.",
            }

        previous_period, previous_value = monthly_data[-2]
        current_period, current_value = monthly_data[-1]

        if previous_value is None or current_value is None:
            return {
                "available": False,
                "reason": "One of the two most recent periods is missing a value.",
                "previous_period": previous_period,
                "current_period": current_period,
            }

        change = current_value - previous_value
        if previous_value == 0:
            return {
                "available": True,
                "reason": "zero_baseline",
                "previous_period": previous_period,
                "current_period": current_period,
                "previous_value": previous_value,
                "current_value": current_value,
                "change": change,
                "change_percent": None,
            }

        return {
            "available": True,
            "reason": None,
            "previous_period": previous_period,
            "current_period": current_period,
            "previous_value": previous_value,
            "current_value": current_value,
            "change": change,
            "change_percent": round((change / previous_value) * 100, 2),
        }
