import math
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

    # -- Richer, evidence-backed anomaly output. detect_z_score()
    # above is untouched (existing callers keep its exact tuple-list
    # shape); this is a new, opt-in method that returns a structured
    # result with baseline/deviation/context/reason per anomaly, plus
    # an explicit status for every case that isn't a crash but also
    # isn't a normal detection run (unsupported column, too few
    # observations, zero variance).

    def detect_with_context(
        self,
        column,
        threshold=2.0,
        table_name="sales",
        dimension_column=None,
        date_column=None,
    ):
        """Like detect_z_score(), but returns a structured dict with
        mean/standard_deviation, a "status" describing what happened,
        and per-anomaly evidence: baseline, deviation, an optional
        dimension/date context column, and a plain-language reason.
        Never produces NaN/Infinity, never crashes on non-numeric,
        constant, tiny, or missing-value data."""
        supported, reason = self.check_support(column, table_name)
        if not supported:
            return {
                "supported": False,
                "reason": reason,
                "column": column,
                "mean": None,
                "standard_deviation": None,
                "status": "unsupported_column",
                "anomalies": [],
            }

        table_name = safe_table_name(table_name)
        available_columns = get_table_columns(self.conn, table_name)
        context_columns = [
            c for c in (dimension_column, date_column)
            if c and c in available_columns
        ]
        extra_select = "".join(f", {quote_identifier(c)}" for c in context_columns)

        query = (
            f'SELECT rowid, {quote_identifier(column)}{extra_select} '
            f'FROM {quote_identifier(table_name)} '
            f'WHERE {quote_identifier(column)} IS NOT NULL'
        )
        cursor = self.conn.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()

        numeric_rows = []
        for row in rows:
            rowid, value = row[0], row[1]
            extras = row[2:]
            try:
                numeric_value = float(value)
            except (TypeError, ValueError):
                continue
            if math.isnan(numeric_value) or math.isinf(numeric_value):
                # A non-finite stored value is evidence-less -- skip it
                # rather than let it poison the mean/variance or leak
                # NaN/Infinity into a JSON-safe result downstream.
                continue
            numeric_rows.append((rowid, value, numeric_value, extras))

        if len(numeric_rows) < 2:
            return {
                "supported": True,
                "reason": "Fewer than 2 numeric observations are available for this column.",
                "column": column,
                "mean": None,
                "standard_deviation": None,
                "status": "insufficient_data",
                "anomalies": [],
            }

        values = [item[2] for item in numeric_rows]
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        standard_deviation = variance ** 0.5

        if standard_deviation == 0:
            return {
                "supported": True,
                "reason": "All observed values are identical (zero variance) -- no anomalies to detect.",
                "column": column,
                "mean": round(mean, 4),
                "standard_deviation": 0.0,
                "status": "zero_variance",
                "anomalies": [],
            }

        anomalies = []
        for rowid, original_value, numeric_value, extras in numeric_rows:
            z_score = (numeric_value - mean) / standard_deviation
            if abs(z_score) < threshold:
                continue

            context = {}
            extra_index = 0
            if dimension_column and dimension_column in available_columns:
                context["dimension"] = {"column": dimension_column, "value": extras[extra_index]}
                extra_index += 1
            if date_column and date_column in available_columns:
                context["date"] = {"column": date_column, "value": extras[extra_index]}
                extra_index += 1

            anomalies.append({
                "row_id": rowid,
                "metric": column,
                "value": original_value,
                "baseline": round(mean, 4),
                "z_score": round(z_score, 2),
                "deviation": round(numeric_value - mean, 4),
                "context": context,
                "reason": f"Deviates {round(abs(z_score), 2)} standard deviations from the mean.",
            })

        return {
            "supported": True,
            "reason": None,
            "column": column,
            "mean": round(mean, 4),
            "standard_deviation": round(standard_deviation, 4),
            "status": "ok",
            "anomalies": anomalies,
        }
