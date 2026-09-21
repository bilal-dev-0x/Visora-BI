"""
Shared helpers used by the analytical engines (MetricsEngine, TrendEngine,
ContributionAnalyzer, AnomalyDetector) so each one can check -- before
running a query -- whether the selected table/dataset actually has the
columns it needs, and fail gracefully instead of raising a sqlite
OperationalError.
"""

from backend.sql_safety import safe_table_name, quote_identifier


def table_exists(conn, table_name):
    table_name = safe_table_name(table_name)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    )
    return cursor.fetchone() is not None


def get_table_columns(conn, table_name):
    """Return the list of column names for table_name, or [] if the
    table does not exist."""
    table_name = safe_table_name(table_name)
    if not table_exists(conn, table_name):
        return []
    cursor = conn.execute(f"PRAGMA table_info({quote_identifier(table_name)})")
    return [row[1] for row in cursor.fetchall()]


def missing_columns(conn, table_name, required_columns):
    """Return the subset of required_columns not present in table_name."""
    available = set(get_table_columns(conn, table_name))
    return [column for column in required_columns if column not in available]
