"""
Unified analytical context orchestrator.

analyze_dataset() takes one selected dataset (its ingested SQLite
table_name plus the CSV path DataAnalyzer already knows how to read)
and coordinates the *existing* analytical engines -- DataAnalyzer,
CapabilityDetector, MetricsEngine, TrendEngine, ContributionAnalyzer,
AnomalyDetector -- into a single, JSON-serializable structure:

    Dataset -> DataAnalyzer -> capability detection -> Metrics -> Trends
            -> Contribution -> Anomaly -> unified analytical context

This module performs no analytical calculation of its own. Every
number in the result comes from an existing engine; this file only
decides *which* columns to hand each engine (using CapabilityDetector's
suggestions), calls it, and assembles/serializes the combined result.
It is deliberately the foundation for the AI context pipeline, not
a second reporting system -- DataAnalyzer.build_report()/export_report()
are untouched and keep working exactly as before.
"""

import math
from datetime import date, datetime

import pandas as pd

from backend.analyzer import DataAnalyzer
from backend.anomaly import AnomalyDetector
from backend.capabilities import CapabilityDetector
from backend.contribution import ContributionAnalyzer
from backend.metrics import MetricsEngine
from backend.trends import TrendEngine

DB_FILE = "data/visora.db"

# Coordination-layer limits only -- these bound how much the
# orchestrator *asks* the existing engines for, so the resulting
# context stays a reasonable size for a future AI prompt. They do not
# change how any engine calculates its results.
_MAX_METRIC_COLUMNS = 8
_MAX_ANOMALY_COLUMNS = 5
_MAX_CONTRIBUTION_ROWS = 25


def _unsupported(reason):
    return {"available": False, "data": None, "reason": reason}


def _supported(data):
    return {"available": True, "data": data, "reason": None}


def _error(exc):
    return {"available": False, "data": None, "reason": f"Error: {exc}"}


def _json_safe(value):
    """Recursively coerce value into something json.dumps can handle,
    covering everything the existing engines / pandas / numpy can hand
    back: numpy scalars (int64, float64, bool_), pandas Timestamp/NaT,
    NaN, +-inf, and tuples (e.g. ContributionAnalyzer/AnomalyDetector
    rows)."""
    if isinstance(value, dict):
        return {str(key): _json_safe(val) for key, val in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bool):
        return value
    if hasattr(value, "item") and not isinstance(value, str):
        # numpy scalar types (int64, float64, bool_, ...)
        try:
            value = value.item()
        except (TypeError, ValueError):
            pass
    if isinstance(value, float):
        return None if (math.isnan(value) or math.isinf(value)) else value
    if isinstance(value, (int, str)):
        return value
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return str(value)


def _run_data_analyzer(csv_path):
    analyzer = DataAnalyzer(csv_path)
    analyzer.load_data()
    analyzer.get_basic_information()
    analyzer.get_quality_checks()
    analyzer.get_other_details()
    return analyzer


def _build_metrics(engine, capability, table_name):
    if not capability["metrics"]["available"]:
        return _unsupported(capability["metrics"]["reason"])

    columns = capability["candidate_measures"][:_MAX_METRIC_COLUMNS]
    per_column = {}
    for column in columns:
        try:
            per_column[column] = {
                "sum": engine.get_sum(column, table_name=table_name),
                "average": engine.get_average(column, table_name=table_name),
                "min": engine.get_min(column, table_name=table_name),
                "max": engine.get_max(column, table_name=table_name),
                "count": engine.get_count(column, table_name=table_name),
            }
        except Exception as exc:  # a single bad column should not sink the rest
            per_column[column] = {"error": str(exc)}
    return _supported(per_column)


def _build_trends(engine, capability, table_name):
    trend_capability = capability["trends"]
    if not trend_capability["available"]:
        return _unsupported(trend_capability["reason"])

    # Generic engine methods: work for any date_column +
    # measure_column pair capability detection found -- the
    # business-specific "Order Date"/"Sales" pair included, since it's
    # just one more valid (date, measure) combination to them.
    date_column = trend_capability["date_column"]
    measure_column = trend_capability["measure_column"]

    try:
        monthly = engine.get_monthly_metrics_generic(date_column, measure_column, table_name=table_name)
        growth = engine.calculate_growth_generic(monthly)
        moving_average = engine.calculate_moving_average_generic(monthly)
        period_comparison = engine.compare_last_two_periods_generic(monthly)
    except Exception as exc:
        return _error(exc)

    return _supported({
        "date_column": date_column,
        "measure_column": measure_column,
        "monthly": [{"period": period, "value": value} for period, value in monthly],
        "growth": growth,
        "moving_average": moving_average,
        "period_comparison": period_comparison,
    })


def _build_contribution(engine, capability, table_name):
    contribution_capability = capability["contribution"]
    if not contribution_capability["available"]:
        return _unsupported(contribution_capability["reason"])

    dimension = contribution_capability["dimension"]
    measure = contribution_capability["measure"]
    try:
        result = engine.analyze_with_metadata(
            dimension, measure, table_name=table_name, top_n=_MAX_CONTRIBUTION_ROWS,
        )
    except Exception as exc:
        return _error(exc)

    if not result["supported"]:
        return _unsupported(result["reason"])

    return _supported({
        "dimension": dimension,
        "measure": measure,
        "total_categories": result["total_categories"],
        "rows_truncated": result["rows_truncated"],
        "truncation_reason": result["truncation_reason"],
        # Each entry: {"category", "value", "percent", "rank"}
        "breakdown": result["breakdown"],
    })


def _build_anomalies(engine, capability, table_name):
    if not capability["anomaly"]["available"]:
        return _unsupported(capability["anomaly"]["reason"])

    columns = capability["candidate_measures"][:_MAX_ANOMALY_COLUMNS]
    per_column = {}
    for column in columns:
        try:
            result = engine.detect_with_context(column, table_name=table_name)
            # Each anomaly dict already carries row_id/metric/value/
            # baseline/z_score/deviation/context/reason -- pass through
            # as-is (or [] for any non-"ok" but non-crashing status,
            # e.g. zero_variance/insufficient_data).
            per_column[column] = result["anomalies"] if result["supported"] else []
        except Exception as exc:
            per_column[column] = {"error": str(exc)}
    return _supported(per_column)


def analyze_dataset(table_name, csv_path, db_file=DB_FILE, dataset_metadata=None):
    """Analyze one selected dataset and return a single, JSON-safe
    unified analytical context dict.

    table_name: the SQLite table the dataset was ingested into
        (backend/ingestion.py's DatasetIngestor).
    csv_path: path to the dataset's persisted CSV, used for the
        structural/data-quality pass (backend/analyzer.py's
        DataAnalyzer) exactly as the rest of the app already does.
    dataset_metadata: optional registry row (backend/dataset_registry.py)
        -- dataset_id / original_filename / row_count / column_count --
        included verbatim when available; derived from the data itself
        otherwise.

    Never raises for an unsupported or malformed dataset: every
    capability section is either {"available": true, "data": ...} or
    {"available": false, "data": null, "reason": "..."}.
    """
    analyzer = _run_data_analyzer(csv_path)

    capability_detector = CapabilityDetector(db_file)
    capability_detector.connect()
    capability = capability_detector.detect(table_name)

    metrics_engine = MetricsEngine(db_file)
    metrics_engine.connect()
    trend_engine = TrendEngine(db_file)
    trend_engine.connect()
    contribution_engine = ContributionAnalyzer(db_file)
    contribution_engine.connect()
    anomaly_engine = AnomalyDetector(db_file)
    anomaly_engine.connect()

    context = {
        "dataset": {
            "dataset_id": (dataset_metadata or {}).get("dataset_id"),
            "original_filename": (dataset_metadata or {}).get("original_filename"),
            "table_name": table_name,
            "row_count": (dataset_metadata or {}).get("row_count", len(analyzer.df)),
            "column_count": (dataset_metadata or {}).get("column_count", len(analyzer.columns)),
        },
        "schema": {
            "columns": analyzer.columns,
            "numeric_columns": analyzer.numeric_columns,
            "categorical_columns": analyzer.categorical_columns,
            "date_columns": analyzer.date_columns,
            "candidate_measures": capability["candidate_measures"],
            "candidate_dimensions": capability["candidate_dimensions"],
        },
        "data_quality": {
            "total_missing_values": analyzer.total_missing_values,
            "columns_with_missing_values": analyzer.columns_with_missing_values,
            "duplicate_rows": analyzer.duplicate_rows,
            "completely_empty_rows": analyzer.completely_empty_rows,
            "column_health": analyzer.get_column_health(),
        },
        "numeric_statistics": analyzer.get_numeric_statistics(),
        "capabilities": {
            "metrics": {"available": capability["metrics"]["available"], "reason": capability["metrics"]["reason"]},
            "trends": {
                "available": capability["trends"]["available"],
                "reason": capability["trends"]["reason"],
                "date_column": capability["trends"]["date_column"],
                "measure_column": capability["trends"]["measure_column"],
            },
            "contribution": {
                "available": capability["contribution"]["available"],
                "reason": capability["contribution"]["reason"],
            },
            "anomaly": {"available": capability["anomaly"]["available"], "reason": capability["anomaly"]["reason"]},
        },
        "metrics": _build_metrics(metrics_engine, capability, table_name),
        "trends": _build_trends(trend_engine, capability, table_name),
        "contribution": _build_contribution(contribution_engine, capability, table_name),
        "anomalies": _build_anomalies(anomaly_engine, capability, table_name),
    }

    return _json_safe(context)
