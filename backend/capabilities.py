"""
Schema-driven capability detection (Day 1).

Given a table_name that has already been ingested into SQLite by
DatasetIngestor, CapabilityDetector inspects the dataset's *actual*
schema -- not a hardcoded assumption of "Order Date" / "Sales" /
"Profit" -- and reports which analytical capabilities are usable for
it, plus which columns are reasonable candidates for each one.

This module never performs analytical calculations and never
duplicates an existing engine's logic. It only:
    * reads column names/types via backend/engine_support.py
    * reuses TrendEngine.check_support() for the one capability
      (business-specific trend analysis) that has a fixed, non-generic
      requirement (Order Date + Sales), instead of re-deriving that
      rule here
    * runs simple, read-only COUNT/DISTINCT queries to size up columns
      well enough to suggest sensible candidates

Generic MetricsEngine aggregation, ContributionAnalyzer grouping, and
AnomalyDetector z-score detection all work on *any* schema (they take
column names as arguments), so "available" for those simply means
"a suitable column exists" -- it does not hardcode any particular
dataset's fields.
"""

import sqlite3

import pandas as pd

from backend.engine_support import table_exists
from backend.sql_safety import quote_identifier, safe_table_name
from backend.trends import TrendEngine

# SQLite type affinities produced by DatasetIngestor._infer_sqlite_type():
# bool/int -> INTEGER, float -> REAL, datetime -> TEXT (stored as ISO
# text), everything else -> TEXT. So "numeric" here means INTEGER/REAL.
_NUMERIC_AFFINITIES = ("INTEGER", "REAL")

# A text column is only treated as date-like if this fraction (or more)
# of its non-null values parse cleanly as dates -- mirrors the ratio
# DatasetIngestor._try_parse_object_dates() already uses at ingestion
# time, so capability detection stays consistent with how the data was
# actually stored. (A compact numeric date encoding, e.g. YYYYMMDD, is
# handled earlier by DatasetIngestor._try_parse_compact_numeric_dates()
# at ingest time, so by the time capability detection runs, such a
# column is already stored as TEXT and reaches this same check.)
_DATE_LIKE_SUCCESS_RATIO = 0.9
_DATE_SAMPLE_SIZE = 200

# A categorical column is only offered as a candidate *dimension* (for
# contribution analysis) if it has more than one distinct value, fewer
# distinct values than rows (i.e. at least one value repeats, so
# grouping by it actually aggregates something), and a cardinality low
# enough that grouping by it is meaningful rather than an exploded
# one-row-per-value listing (e.g. an ID column).
_MAX_DIMENSION_CARDINALITY = 50


class CapabilityDetector:
    """Inspects a table's real SQLite schema and reports, per
    analytical capability, whether it is usable for that table --
    without ever running the analysis itself."""

    def __init__(self, db_file="data/visora.db"):
        self.db_file = db_file
        self.conn = None

    def connect(self):
        self.conn = sqlite3.connect(self.db_file)
        return self.conn

    def detect(self, table_name):
        """Return a plain dict describing the table's schema and which
        analytical capabilities apply to it. Never raises for a missing
        table, an empty table, or an unusual schema -- always returns a
        structured, explained result instead."""
        table_name = safe_table_name(table_name)

        if not table_exists(self.conn, table_name):
            reason = f"Table '{table_name}' does not exist."
            return self._empty_result(table_name, reason)

        row_count = self._row_count(table_name)
        column_types = self._column_types(table_name)

        if not column_types:
            return self._empty_result(table_name, "The dataset has no columns.")

        numeric_columns = [
            column for column, sql_type in column_types.items()
            if sql_type in _NUMERIC_AFFINITIES
        ]
        other_columns = [
            column for column in column_types
            if column not in numeric_columns
        ]

        date_columns = [
            column for column in other_columns
            if self._looks_like_date(table_name, column)
        ]
        categorical_columns = [
            column for column in other_columns if column not in date_columns
        ]

        candidate_measures = list(numeric_columns)
        candidate_dimensions = self._candidate_dimensions(
            table_name, categorical_columns, row_count
        )

        metrics_available = bool(numeric_columns) and row_count > 0
        metrics = {
            "available": metrics_available,
            "reason": None if metrics_available else
                "No numeric column with data is available to aggregate.",
        }

        trend_engine = TrendEngine(self.db_file)
        trend_engine.conn = self.conn
        # Prefer the specialized "Order Date"/"Sales" pair when it's
        # actually present (keeps the exact historical reason text for
        # datasets that have neither column, e.g. "Missing required
        # column(s) for trend analysis: Order Date, Sales"). Otherwise
        # fall back to Day 2's generic detection: any date-like column
        # paired with any numeric measure -- e.g. "Date" + "Revenue" is
        # now a valid trend capability even though it isn't the
        # business-specific "Order Date" + "Sales" combination.
        legacy_supported, legacy_reason = trend_engine.check_support(table_name)
        if legacy_supported:
            trend_date_column, trend_measure_column = "Order Date", "Sales"
            trend_supported, trend_reason = True, None
        else:
            trend_date_column, trend_measure_column = self._best_trend_pair(
                date_columns, candidate_measures
            )
            trend_supported = trend_date_column is not None and trend_measure_column is not None
            trend_reason = None if trend_supported else legacy_reason
        trends = {
            "available": trend_supported,
            "reason": trend_reason,
            "date_column": trend_date_column,
            "measure_column": trend_measure_column,
        }

        dimension, measure = self._best_contribution_pair(
            candidate_dimensions, candidate_measures
        )
        contribution_available = dimension is not None and measure is not None
        contribution = {
            "available": contribution_available,
            "reason": None if contribution_available else
                "No suitable categorical dimension + numeric measure pair was found.",
            "dimension": dimension,
            "measure": measure,
        }

        anomaly_available = bool(numeric_columns) and row_count >= 2
        anomaly = {
            "available": anomaly_available,
            "reason": None if anomaly_available else
                "At least one numeric column with 2 or more rows is required.",
        }

        return {
            "table_name": table_name,
            "exists": True,
            "row_count": row_count,
            "column_count": len(column_types),
            "numeric_columns": numeric_columns,
            "categorical_columns": categorical_columns,
            "date_columns": date_columns,
            "candidate_measures": candidate_measures,
            "candidate_dimensions": candidate_dimensions,
            "metrics": metrics,
            "trends": trends,
            "contribution": contribution,
            "anomaly": anomaly,
        }

    # -- internals ---------------------------------------------------

    def _empty_result(self, table_name, reason):
        return {
            "table_name": table_name,
            "exists": False,
            "row_count": 0,
            "column_count": 0,
            "numeric_columns": [],
            "categorical_columns": [],
            "date_columns": [],
            "candidate_measures": [],
            "candidate_dimensions": [],
            "metrics": {"available": False, "reason": reason},
            "trends": {"available": False, "reason": reason, "date_column": None, "measure_column": None},
            "contribution": {"available": False, "reason": reason, "dimension": None, "measure": None},
            "anomaly": {"available": False, "reason": reason},
        }

    def _row_count(self, table_name):
        cursor = self.conn.execute(
            f"SELECT COUNT(*) FROM {quote_identifier(table_name)}"
        )
        return int(cursor.fetchone()[0])

    def _column_types(self, table_name):
        cursor = self.conn.execute(
            f"PRAGMA table_info({quote_identifier(table_name)})"
        )
        # PRAGMA table_info columns: (cid, name, type, notnull, dflt_value, pk)
        return {row[1]: (row[2] or "").upper() for row in cursor.fetchall()}

    def _looks_like_date(self, table_name, column):
        """Best-effort, schema-agnostic date detection for a TEXT
        column, mirroring the ratio-based heuristic ingestion already
        applies -- a column only counts as date-like if the large
        majority of a sample actually parses as a date."""
        cursor = self.conn.execute(
            f"SELECT {quote_identifier(column)} FROM {quote_identifier(table_name)} "
            f"WHERE {quote_identifier(column)} IS NOT NULL LIMIT {_DATE_SAMPLE_SIZE}"
        )
        values = [row[0] for row in cursor.fetchall()]
        if not values:
            return False
        parsed = pd.to_datetime(pd.Series(values), errors="coerce", format="mixed")
        success_ratio = parsed.notna().mean()
        return bool(success_ratio >= _DATE_LIKE_SUCCESS_RATIO)

    def _candidate_dimensions(self, table_name, categorical_columns, row_count):
        if row_count == 0:
            return []
        candidates = []
        for column in categorical_columns:
            cursor = self.conn.execute(
                f"SELECT COUNT(DISTINCT {quote_identifier(column)}) "
                f"FROM {quote_identifier(table_name)}"
            )
            distinct_count = cursor.fetchone()[0]
            if 1 < distinct_count < row_count and distinct_count <= _MAX_DIMENSION_CARDINALITY:
                candidates.append(column)
        return candidates

    def _best_contribution_pair(self, candidate_dimensions, candidate_measures):
        if not candidate_dimensions or not candidate_measures:
            return None, None
        return candidate_dimensions[0], candidate_measures[0]

    def _best_trend_pair(self, date_columns, candidate_measures):
        """Pick a deterministic (date_column, measure_column) pair for
        generic trend analysis: the first detected date-like column
        together with the first candidate numeric measure. Schema-
        agnostic -- never assumes "Order Date" or "Sales" by name."""
        if not date_columns or not candidate_measures:
            return None, None
        return date_columns[0], candidate_measures[0]
