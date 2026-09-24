"""
Report file lifecycle (Day 4).

Two on-disk report representations, per the Day 4 spec:

    A. Unified JSON -- ONE current file (reports/current_report.json),
       always representing the most recently produced unified report.
       Re-analyzing (this dataset or a different one) replaces it in
       place; VISORA never accumulates timestamped/obsolete JSON
       files. The structured backend result remains the source of
       truth either way -- this file is a convenience snapshot, not a
       second source of truth.

    B. Human-readable TXT -- one file PER dataset
       (reports/<safe-name>.txt), so multiple datasets' reports can
       coexist and be downloaded independently. Re-analyzing the same
       dataset overwrites its own TXT file rather than creating a new
       timestamped one (unlike the legacy
       backend/analyzer.py:export_report(), which is intentionally
       left untouched for scripts/cli_report.py's standalone use).

Filenames are derived from the dataset's original filename (for
readability) plus its dataset_id (for guaranteed uniqueness across
datasets that happen to share a display name) -- never from a
timestamp, so there is exactly one TXT file per dataset at any time.

delete_txt_report() and delete_current_json_if_for_dataset() are used
by backend/pipeline.py so a deleted dataset never leaves an orphan .txt
or stale current JSON file behind, and no other dataset's report is
touched.
"""

import json
import re
from pathlib import Path

REPORTS_DIR = Path("reports")
CURRENT_JSON_FILENAME = "current_report.json"

_SAFE_STEM_RE = re.compile(r"[^A-Za-z0-9_-]+")


def _sanitize_stem(stem):
    stem = _SAFE_STEM_RE.sub("_", str(stem)).strip("_")
    return stem or "dataset"


def txt_report_path(dataset, reports_dir=None):
    """Deterministic, collision-safe TXT report path for a dataset
    registry row (must carry at least 'dataset_id'; 'original_filename'
    is used for readability when present)."""
    reports_dir = REPORTS_DIR if reports_dir is None else reports_dir
    dataset_id = dataset.get("dataset_id", "")
    original_filename = dataset.get("original_filename") or "dataset"
    stem = _sanitize_stem(Path(str(original_filename)).stem)
    short_id = dataset_id.replace("-", "")[:8] or "unknown"
    return Path(reports_dir) / f"{stem}_{short_id}.txt"


def current_json_path(reports_dir=None):
    reports_dir = REPORTS_DIR if reports_dir is None else reports_dir
    return Path(reports_dir) / CURRENT_JSON_FILENAME


def save_current_json(report, reports_dir=None):
    """Overwrite the single current unified JSON report. Never raises
    on a serialization hiccup -- the caller's in-memory report is what
    actually drives the UI; this file is a best-effort snapshot."""
    path = current_json_path(reports_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return str(path)
    except (OSError, TypeError, ValueError):
        return None


def load_current_json(reports_dir=None):
    path = current_json_path(reports_dir)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _format_priority_line(item):
    priority = (item.get("priority") or "low").upper()
    return f"  [{priority}] {item.get('title')}"


def render_txt(report):
    """Render a unified final report (see backend/pipeline.py) as
    plain, human-readable text. Reads only fields already present on
    the report -- never recalculates or invents anything."""
    dataset = report.get("dataset") or {}
    lines = []
    lines.append("=" * 70)
    lines.append(f"VISORA BI -- Analysis Report: {dataset.get('original_filename', 'Unknown dataset')}")
    lines.append("=" * 70)
    lines.append(f"Generated: {report.get('generated_at', 'unknown')}")
    lines.append(f"Status: {report.get('status', 'unknown')}")
    lines.append(f"Rows: {dataset.get('row_count', '—')}    Columns: {dataset.get('column_count', '—')}")
    lines.append("")

    quality = report.get("data_quality") or {}
    lines.append("-- Data Quality --")
    lines.append(f"Missing values: {quality.get('total_missing_values', '—')}")
    lines.append(f"Duplicate rows: {quality.get('duplicate_rows', '—')}")
    lines.append(f"Completely empty rows: {quality.get('completely_empty_rows', '—')}")
    lines.append("")

    findings = report.get("prioritized_findings") or []
    lines.append("-- Prioritized Findings --")
    if findings:
        for item in findings:
            lines.append(_format_priority_line(item))
    else:
        lines.append("  No notable findings were detected.")
    lines.append("")

    ai_analysis = report.get("ai_analysis") or {}
    lines.append("-- AI Analysis --")
    lines.append(f"Source: {ai_analysis.get('source', 'unknown')}")
    lines.append(ai_analysis.get("summary", "No summary available."))
    risks = ai_analysis.get("risks") or []
    if risks:
        lines.append("")
        lines.append("Risks:")
        for risk in risks:
            lines.append(f"  - {risk}")
    opportunities = ai_analysis.get("opportunities") or []
    if opportunities:
        lines.append("")
        lines.append("Opportunities:")
        for opportunity in opportunities:
            lines.append(f"  - {opportunity}")
    lines.append("")
    lines.append("=" * 70)

    return "\n".join(lines)


def save_txt_report(dataset, report, reports_dir=None):
    """Write (overwrite) this dataset's TXT report. Returns the path
    written, or None if writing failed -- never raises, since a
    report-export failure must not take down the analysis pipeline."""
    path = txt_report_path(dataset, reports_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_txt(report), encoding="utf-8")
        return str(path)
    except OSError:
        return None


def delete_txt_report(dataset, reports_dir=None):
    """Delete this dataset's TXT report, if it exists.

    Returns ``True`` when a file was removed and ``False`` when it was
    already absent. Other filesystem errors are deliberately allowed to
    propagate so the caller can tell the user that lifecycle cleanup did
    not fully succeed instead of silently reporting a successful delete.
    Only the deterministic path for ``dataset`` is touched.
    """
    path = txt_report_path(dataset, reports_dir)
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False


def delete_current_json(reports_dir=None):
    """Delete the global current JSON snapshot.

    Returns ``True`` when it was removed and ``False`` when it was
    already absent. Permission and other filesystem errors propagate to
    the lifecycle coordinator.
    """
    path = current_json_path(reports_dir)
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False


def delete_current_json_if_for_dataset(dataset_id, reports_dir=None):
    """Remove ``current_report.json`` only when it represents ``dataset_id``.

    A valid current report for a different dataset is left untouched. If
    the current file exists but cannot be read or does not identify a
    dataset, this function raises instead of guessing: selective deletion
    must not risk deleting another dataset's snapshot or leaving an
    unverifiable stale file behind.
    """
    path = current_json_path(reports_dir)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return False
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"Could not verify {path.name}; refusing selective deletion because "
            "its represented dataset is unknown."
        ) from exc

    represented_id = (payload.get("dataset") or {}).get("dataset_id") if isinstance(payload, dict) else None
    if not represented_id:
        raise ValueError(
            f"Could not identify the dataset represented by {path.name}; "
            "refusing selective deletion."
        )

    if represented_id != dataset_id:
        return False
    return delete_current_json(reports_dir)


def txt_report_exists(dataset, reports_dir=None):
    return txt_report_path(dataset, reports_dir).exists()
