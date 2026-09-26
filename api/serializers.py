"""Turn existing backend artifacts into JSON-safe API payloads.

Nothing here recomputes analytics: it reads what ``backend/`` already
produced (registry rows, unified reports, DataAnalyzer profiles) and
reshapes it for the React client.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from backend import report_store

_INTERNAL_KEYS = ("stored_path", "table_name", "db_file", "storage_dir")


def json_scalar(value: Any) -> Any:
    """Coerce pandas/numpy scalars into plain JSON-safe Python values."""
    if value is None:
        return None
    try:
        import pandas as pd

        if value is pd.NaT or (isinstance(value, float) and math.isnan(value)):
            return None
        if isinstance(value, pd.Timestamp):
            return value.isoformat()
    except Exception:  # pragma: no cover - pandas always available at runtime
        pass
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        try:
            return json_scalar(value.item())
        except Exception:
            pass
    if isinstance(value, dict):
        return {str(k): json_scalar(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_scalar(v) for v in value]
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    if isinstance(value, float):
        return None if math.isnan(value) or math.isinf(value) else value
    return str(value)


def _stat_size(path: Optional[Path]) -> Optional[int]:
    try:
        if path and Path(path).exists():
            return Path(path).stat().st_size
    except OSError:
        return None
    return None


def _mtime_iso(path: Optional[Path]) -> Optional[str]:
    try:
        if path and Path(path).exists():
            return datetime.fromtimestamp(
                Path(path).stat().st_mtime, tz=timezone.utc
            ).isoformat()
    except OSError:
        return None
    return None


def dataset_status(row: dict) -> str:
    if not row.get("stored_path") or not Path(row["stored_path"]).exists():
        return "needs_attention"
    if row.get("row_count") is None:
        return "needs_attention"
    # Ingestion failures persist 0 rows / 0 columns (same contract the
    # Streamlit dashboard uses); the file exists but could not be loaded.
    if row.get("row_count") == 0 and row.get("column_count") == 0:
        return "needs_attention"
    return "ready"


def serialize_dataset(row: dict) -> dict:
    """Public dataset shape shared by list, detail, and upload responses."""
    created = row.get("created_at")
    if isinstance(created, datetime):
        created = created.isoformat()
    path = row.get("stored_path")
    txt_path = None
    try:
        txt_path = report_store.txt_report_path(row)
    except Exception:
        txt_path = None
    return {
        "id": row.get("dataset_id"),
        "fileName": row.get("original_filename"),
        "displayName": _display_name(row.get("original_filename")),
        "rowCount": row.get("row_count"),
        "columnCount": row.get("column_count"),
        "createdAt": created,
        "sizeBytes": _stat_size(Path(path) if path else None),
        "sha256": row.get("sha256"),
        "status": dataset_status(row),
        "reportAvailable": bool(txt_path and Path(txt_path).exists()),
    }


def _display_name(filename: Optional[str]) -> str:
    if not filename:
        return "Untitled dataset"
    return Path(filename).stem or filename


def build_dataset_profile(row: dict) -> dict:
    """Profile + preview built through the existing DataAnalyzer."""
    from backend.analyzer import DataAnalyzer

    path = row.get("stored_path")
    result: dict[str, Any] = {
        "available": False,
        "reason": None,
        "preview": None,
        "previewColumns": [],
        "quality": None,
        "columnHealth": [],
        "statistics": None,
    }
    if not path or not Path(path).exists():
        result["reason"] = "stored_file_missing"
        return result
    try:
        analyzer = DataAnalyzer(path)
        analyzer.load_data()
        analyzer.get_basic_information()
        analyzer.get_quality_checks()
        analyzer.get_other_details()
        column_health = analyzer.get_column_health()
        numeric_stats = analyzer.get_numeric_statistics()
        categorical_stats = analyzer.get_categorical_distributions()
        frame = analyzer.df
        preview_frame = frame.head(20)
        result["previewColumns"] = [str(c) for c in preview_frame.columns]
        result["preview"] = [
            [json_scalar(cell) for cell in record]
            for record in preview_frame.to_dict(orient="records")
        ]
        result["quality"] = {
            "missingValues": int(analyzer.total_missing_values),
            "missingColumns": [str(c) for c in analyzer.columns_with_missing_values],
            "duplicateRows": int(analyzer.duplicate_rows),
            "emptyRows": int(analyzer.completely_empty_rows),
        }
        result["columnHealth"] = json_scalar(column_health)
        result["statistics"] = json_scalar(
            {
                "numeric": numeric_stats,
                "categorical": categorical_stats,
                "dateColumns": analyzer.date_columns,
                "categoricalColumns": analyzer.categorical_columns,
            }
        )
        result["available"] = True
    except Exception as exc:  # malformed / non-CSV content
        result["reason"] = "unreadable_file"
        result["detail"] = str(exc)
    return result


def serialize_report_summary(dataset_row: Optional[dict]) -> Optional[dict]:
    if not dataset_row:
        return None
    try:
        txt_path = report_store.txt_report_path(dataset_row)
    except Exception:
        return None
    if not txt_path or not Path(txt_path).exists():
        return None
    return {
        "id": f"txt::{dataset_row.get('dataset_id')}",
        "datasetId": dataset_row.get("dataset_id"),
        "fileName": Path(txt_path).name,
        "displayName": _display_name(dataset_row.get("original_filename")),
        "kind": "text",
        "sizeBytes": _stat_size(Path(txt_path)),
        "generatedAt": _mtime_iso(Path(txt_path)),
        "downloadUrl": f"/api/v1/reports/{dataset_row.get('dataset_id')}/text",
    }


def list_reports(registry) -> dict:
    reports = []
    rows = registry.list_datasets()
    for row in rows:
        summary = serialize_report_summary(row)
        if summary:
            reports.append(summary)
    current = report_store.load_current_json()
    current_path = Path(report_store.REPORTS_DIR) / report_store.CURRENT_JSON_FILENAME
    current_meta = None
    if current:
        dataset_id = (current.get("dataset") or {}).get("dataset_id")
        current_meta = {
            "id": "unified::current",
            "datasetId": dataset_id,
            "fileName": report_store.CURRENT_JSON_FILENAME,
            "displayName": "Unified analysis",
            "kind": "unified",
            "sizeBytes": _stat_size(current_path),
            "generatedAt": current.get("generated_at") or _mtime_iso(current_path),
            "downloadUrl": None,
        }
    return {"reports": reports, "current": current_meta}


def _metric(report: dict, section: str) -> dict:
    value = report.get(section)
    if isinstance(value, dict) and value.get("available"):
        return value.get("data") or {}
    return {}


def build_overview(registry) -> dict:
    rows = registry.list_datasets()
    datasets = [serialize_dataset(r) for r in rows]
    report = report_store.load_current_json() or {}
    metrics = _metric(report, "metrics")
    trends = _metric(report, "trends")
    contribution = _metric(report, "contribution")
    anomalies = _metric(report, "anomalies")
    evidence = report.get("evidence") or []
    findings = report.get("prioritized_findings") or []
    ai = report.get("ai_analysis") or {}
    dataset_meta = report.get("dataset") or {}

    total_rows = sum(r.get("rowCount") or 0 for r in datasets)
    ready = [r for r in datasets if r.get("status") == "ready"]
    critical = [f for f in findings if f.get("priority") == "critical"]
    quality = _quality_score(report)

    trend_series = [
        {"period": item.get("period"), "value": json_scalar(item.get("value"))}
        for item in trends.get("monthly", [])
    ]
    contribution_rows = contribution.get("breakdown") or []
    contribution_series = [
        {
            "label": json_scalar(item.get("category")),
            "value": json_scalar(item.get("value")),
            "percent": json_scalar(item.get("percent")),
        }
        for item in contribution_rows
    ]

    anomaly_count = 0
    if isinstance(anomalies, dict):
        for value in anomalies.values():
            if isinstance(value, list):
                anomaly_count += len(value)

    return {
        "datasets": {
            "total": len(datasets),
            "ready": len(ready),
            "totalRows": total_rows,
            "recent": datasets[:4],
        },
        "kpis": [
            {
                "id": "rows",
                "label": "Rows analyzed",
                "value": total_rows,
                "format": "int",
                "tone": "neutral",
            },
            {
                "id": "columns",
                "label": "Active columns",
                "value": dataset_meta.get("column_count") or _latest_column_count(datasets),
                "format": "int",
                "tone": "neutral",
            },
            {
                "id": "findings",
                "label": "Critical findings",
                "value": len(critical),
                "format": "int",
                "tone": "critical" if critical else "positive",
            },
            {
                "id": "quality",
                "label": "Data quality",
                "value": quality,
                "format": "percent",
                "tone": "positive" if quality >= 90 else "warning",
            },
        ],
        "trend": {
            "datasetId": dataset_meta.get("dataset_id"),
            "measure": trends.get("measure_column"),
            "dateColumn": trends.get("date_column"),
            "series": trend_series,
            "available": bool(trend_series),
        },
        "contribution": {
            "dimension": contribution.get("dimension"),
            "measure": contribution.get("measure"),
            "series": contribution_series,
            "available": bool(contribution_series),
        },
        "anomalies": {
            "count": anomaly_count,
            "available": bool(anomalies) and anomaly_count > 0,
        },
        "findings": {
            "total": len(findings),
            "critical": len(critical),
            "items": findings[:5],
        },
        "insights": {
            "summary": ai.get("summary"),
            "source": report.get("ai_analysis", {}).get("source"),
            "count": len(ai.get("insights") or []),
        },
        "reports": list_reports(registry),
        "generatedAt": report.get("generated_at"),
        "available": bool(report),
        "reason": None if report else "no_analysis_yet",
    }


def _latest_column_count(datasets: list[dict]) -> Optional[int]:
    for item in datasets:
        if item.get("columnCount") is not None:
            return item["columnCount"]
    return None


def _quality_score(report: dict) -> int:
    quality = report.get("data_quality")
    if isinstance(quality, dict):
        missing = quality.get("total_missing_values")
        duplicates = quality.get("duplicate_rows")
        rows = (report.get("dataset") or {}).get("row_count") or 0
        if missing is None and duplicates is None:
            return 0
        score = 100.0
        if rows and missing is not None:
            score -= min(60.0, (missing / max(rows, 1)) * 60)
        if rows and duplicates is not None:
            score -= min(30.0, (duplicates / max(rows, 1)) * 30)
        return int(round(max(0.0, min(100.0, score))))
    return 0


def build_insights(registry) -> dict:
    report = report_store.load_current_json()
    if not report:
        return {
            "available": False,
            "reason": "no_analysis_yet",
            "dataset": None,
            "summary": None,
            "source": None,
            "providerUsed": None,
            "skippedReason": None,
            "attempts": [],
            "insights": [],
            "risks": [],
            "opportunities": [],
            "findings": [],
            "evidence": [],
            "analysisStatus": None,
        }
    ai = report.get("ai_analysis") or {}
    attempts = ai.get("attempts") or []
    return {
        "available": True,
        "reason": None,
        "dataset": report.get("dataset"),
        "generatedAt": report.get("generated_at"),
        "summary": ai.get("summary"),
        "source": ai.get("source"),
        "providerUsed": ai.get("provider_used"),
        "skippedReason": ai.get("ai_skipped_reason"),
        "attempts": attempts,
        "insights": ai.get("insights") or [],
        "risks": ai.get("risks") or [],
        "opportunities": ai.get("opportunities") or [],
        "findings": report.get("prioritized_findings") or [],
        "evidence": report.get("evidence") or [],
        "analysisStatus": report.get("status"),
    }
