import sqlite3

from backend.engine_support import get_table_columns, table_exists
from backend.sql_safety import quote_identifier, safe_table_name

# Hard ceiling on how many distinct dimension values analyze_with_metadata()
# will group by. Protects against a caller pointing contribution analysis
# at a high-cardinality column (an ID column with hundreds of thousands or
# millions of unique values) and generating an absurd, near-one-row-per-
# record breakdown. This is defense-in-depth: backend/capabilities.py
# already filters high-cardinality columns out of *candidate* dimensions,
# but analyze_with_metadata() can be called directly with any column.
DEFAULT_MAX_CATEGORIES = 500


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

    # -- Ranked/top-N/bottom-N contribution with high-cardinality
    # protection. analyze() above is untouched (existing callers keep
    # its exact tuple-list return shape); this is a richer, opt-in
    # method for callers (backend/analysis_context.py) that want rank,
    # truncation metadata, and a documented reason when a dimension is
    # rejected outright for being too high-cardinality to group by.

    def analyze_with_metadata(
        self,
        dimension,
        measure,
        table_name="sales",
        top_n=None,
        bottom_n=None,
        max_categories=DEFAULT_MAX_CATEGORIES,
    ):
        """Like analyze(), but returns a structured dict with ranking,
        top-N/bottom-N slicing, and explicit high-cardinality
        protection -- never silently builds a huge breakdown, and
        never hides the fact that a dimension was rejected/truncated.

        Performance: this runs a SINGLE grouped-aggregation query
        (rather than a separate COUNT(DISTINCT ...) scan plus analyze()'s
        own SUM + GROUP BY scans), with the high-cardinality cap applied
        as a SQL LIMIT of (max_categories + 1) rows. SQLite still has to
        read every row once to compute the aggregation (unavoidable for
        any GROUP BY without a covering index), but:
          * only one full-table pass happens, not two or three, and
          * the *result set* pulled back into Python is capped at
            max_categories + 1 rows, so a million-distinct-value
            dimension never materializes a million-row Python list just
            to be discarded a moment later.
        When the pair is supported (row count <= max_categories), the
        LIMIT never actually truncated real data, so the fetched rows
        already represent every category -- the overall total (for
        percentages) and bottom-N slicing are both derived from that
        same result set with no further queries.
        """
        supported, reason = self.check_support(dimension, measure, table_name)
        if not supported:
            return {
                "supported": False,
                "reason": reason,
                "dimension": dimension,
                "measure": measure,
                "total_categories": 0,
                "rows_truncated": False,
                "truncation_reason": None,
                "breakdown": [],
            }

        table_name = safe_table_name(table_name)
        probe_query = f'''
            SELECT {quote_identifier(dimension)}, SUM({quote_identifier(measure)}) AS metric_value
            FROM {quote_identifier(table_name)}
            GROUP BY {quote_identifier(dimension)}
            ORDER BY metric_value DESC
            LIMIT ?
        '''
        cursor = self.conn.cursor()
        cursor.execute(probe_query, (max_categories + 1,))
        rows = cursor.fetchall()

        if len(rows) > max_categories:
            return {
                "supported": False,
                "reason": (
                    f"Dimension '{dimension}' has more than {max_categories} unique "
                    f"values, which exceeds the limit for contribution analysis. "
                    f"(Exact count intentionally not computed -- doing so would "
                    f"require a second full-table scan of a dimension already "
                    f"known to be too high-cardinality to use.)"
                ),
                "dimension": dimension,
                "measure": measure,
                "total_categories": None,
                "rows_truncated": True,
                "truncation_reason": "high_cardinality",
                "breakdown": [],
            }

        rows = [
            ("Missing" if category is None else category, value)
            for category, value in rows
            if value is not None
        ]
        total = sum(value for _category, value in rows)

        if not total:
            return {
                "supported": True,
                "reason": "Total value is zero across all categories; no percentage contribution to compute.",
                "dimension": dimension,
                "measure": measure,
                "total_categories": len(rows),
                "rows_truncated": False,
                "truncation_reason": None,
                "breakdown": [],
            }

        ranked = [
            {
                "category": category,
                "value": value,
                "percent": round((value / total) * 100, 2),
                "rank": index + 1,
            }
            for index, (category, value) in enumerate(rows)
        ]

        rows_truncated = False
        truncation_reason = None
        breakdown = ranked
        if top_n is not None and top_n >= 0:
            breakdown = ranked[:top_n]
            if len(ranked) > top_n:
                rows_truncated = True
                truncation_reason = "top_n"
        elif bottom_n is not None and bottom_n >= 0:
            breakdown = ranked[-bottom_n:] if bottom_n else []
            if len(ranked) > bottom_n:
                rows_truncated = True
                truncation_reason = "bottom_n"

        return {
            "supported": True,
            "reason": None,
            "dimension": dimension,
            "measure": measure,
            "total_categories": len(ranked),
            "rows_truncated": rows_truncated,
            "truncation_reason": truncation_reason,
            "breakdown": breakdown,
        }
