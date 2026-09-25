"""
Unified analysis + reporting pipeline.

analyze_dataset(dataset_id) is the ONE backend call the frontend needs
for a fully analyzed, AI-explained, prioritized, report-ready result.
It coordinates modules that already exist (analytical intelligence, AI
provider integration) plus the
layers, without duplicating any of their logic or recalculating
anything they already computed:

    Dataset (registry lookup)
        -> backend.analysis_context.analyze_dataset()   (metrics/
           trends/contribution/anomalies/data-quality/capabilities)
        -> backend.evidence.build_evidence()
        -> backend.prioritization.prioritize_evidence()
        -> backend.ai_service.generate_structured_ai_insights()
           (provider chain / local fallback, structured shape)
        -> unified final report (this module)
        -> backend.report_store persistence

Every capability section keeps the existing {"available", "data",
"reason"} contract untouched. Nothing here is a second reporting
system -- it is the seam that turns the already-existing analytical +
AI layers into the single structured result the dashboard (and any
future API surface) consumes.

Never raises for a missing dataset, an unsupported/malformed CSV, an
ingestion problem, or an AI failure: every failure mode produces a
well-formed result with status != "success" and an explanatory
message, rather than an exception reaching the caller.
"""

from datetime import datetime, timezone
from pathlib import Path

from backend import report_store
from backend.ai_service import generate_structured_ai_insights
from backend.analysis_context import DB_FILE
from backend.analysis_context import analyze_dataset as build_analysis_context
from backend.dataset_registry import DatasetRegistry
from backend.evidence import build_evidence
from backend.prioritization import prioritize_evidence


class DatasetLifecycleError(RuntimeError):
    """A dataset/report lifecycle operation did not fully complete."""


def _lifecycle_error(message, exc):
    return DatasetLifecycleError(f"{message}: {exc}")


def _error_report(dataset_id, message, dataset=None):
    return {
        "dataset": {
            "dataset_id": dataset_id,
            "original_filename": (dataset or {}).get("original_filename"),
            "row_count": (dataset or {}).get("row_count"),
            "column_count": (dataset or {}).get("column_count"),
        },
        "profile": {},
        "data_quality": {},
        "capabilities": {},
        "metrics": {"available": False, "data": None, "reason": message},
        "trends": {"available": False, "data": None, "reason": message},
        "contribution": {"available": False, "data": None, "reason": message},
        "anomalies": {"available": False, "data": None, "reason": message},
        "evidence": [],
        "ai_analysis": {
            "available": False,
            "summary": message,
            "insights": [],
            "risks": [],
            "opportunities": [],
            "source": "unavailable",
        },
        "prioritized_findings": [],
        "status": "error",
        "error": message,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _assemble_final_report(dataset, analysis_context, evidence, prioritized_findings, ai_result):
    report = dict(analysis_context)  # dataset/schema/data_quality/capabilities/metrics/trends/contribution/anomalies
    report["evidence"] = evidence
    report["prioritized_findings"] = prioritized_findings
    report["ai_analysis"] = {
        "available": bool(ai_result.result.get("available", True)),
        "summary": ai_result.result.get("summary"),
        "insights": ai_result.result.get("insights", []),
        "risks": ai_result.result.get("risks", []),
        "opportunities": ai_result.result.get("opportunities", []),
        "source": ai_result.source,
        "provider_used": ai_result.provider_used,
        "ai_skipped_reason": ai_result.ai_skipped_reason,
    }
    report["status"] = "success"
    report["error"] = None
    report["generated_at"] = datetime.now(timezone.utc).isoformat()
    return report


def analyze_dataset(dataset_id, registry=None, db_file=DB_FILE, persist=True):
    """Run the complete unified analysis pipeline for one dataset and return a
    single, JSON-safe unified report (see module docstring for the
    shape). Set persist=False to skip writing the current-JSON /
    per-dataset TXT report files (e.g. for tests or a dry-run/preview
    call) -- analysis itself is unaffected either way.
    """
    owns_registry = registry is None
    if owns_registry:
        registry = DatasetRegistry(db_file=db_file)
        registry.connect()

    try:
        dataset = registry.get_dataset(dataset_id)
        if dataset is None:
            return _error_report(dataset_id, f"No dataset registered with id '{dataset_id}'.")

        csv_path = dataset["stored_path"]
        if not Path(csv_path).exists():
            return _error_report(
                dataset_id,
                "This dataset's underlying file is missing from local storage.",
                dataset=dataset,
            )

        try:
            analysis_context = build_analysis_context(
                dataset["table_name"], csv_path, db_file=db_file, dataset_metadata=dataset,
            )
        except Exception as exc:
            # Belt-and-suspenders: analysis_context.analyze_dataset()
            # already handles unsupported capabilities gracefully, but
            # a truly malformed/unreadable file (e.g. a zero-byte CSV)
            # can still raise before any capability section is built.
            # The unified pipeline must never crash for that -- it
            # reports the failure as a structured, explained result
            # instead.
            return _error_report(dataset_id, f"Could not analyze this dataset: {exc}", dataset=dataset)

        evidence = build_evidence(analysis_context)
        prioritized_findings = prioritize_evidence(evidence)

        try:
            file_size_bytes = Path(csv_path).stat().st_size
        except OSError:
            file_size_bytes = None

        ai_result = generate_structured_ai_insights(
            analysis_context, evidence, prioritized_findings, file_size_bytes=file_size_bytes,
        )

        report = _assemble_final_report(dataset, analysis_context, evidence, prioritized_findings, ai_result)

        if persist:
            report_store.save_current_json(report)
            report_store.save_txt_report(dataset, report)

        return report
    finally:
        pass


def delete_dataset_and_report(dataset_id, registry=None, db_file=DB_FILE):
    """Delete one dataset and only its derived report files.

    The deterministic lifecycle is: remove this dataset's TXT report,
    verify/remove the global current snapshot when it represents this
    dataset, then remove the registry row, analytical table, and stored
    CSV. Other datasets' TXT files and a current report for another live
    dataset are left untouched.

    Returns the deleted registry row, or ``None`` when the dataset does
    not exist. Raises :class:`DatasetLifecycleError` when any cleanup
    step fails so the UI cannot report a false success.
    """
    owns_registry = registry is None
    if owns_registry:
        registry = DatasetRegistry(db_file=db_file)
        registry.connect()

    dataset = registry.get_dataset(dataset_id)
    if dataset is None:
        return None

    label = f"{dataset.get('original_filename') or 'dataset'} ({dataset_id})"
    try:
        report_store.delete_txt_report(dataset)
        # Validate/remove current_report.json before touching the registry
        # row. If it is malformed, selective deletion fails visibly rather
        # than guessing which dataset the global snapshot represents.
        report_store.delete_current_json_if_for_dataset(dataset_id)
        registry.delete_dataset(dataset_id)
    except Exception as exc:
        if isinstance(exc, DatasetLifecycleError):
            raise
        raise _lifecycle_error(f"Could not delete {label}", exc) from exc
    return dataset


def clear_datasets_and_reports(registry=None, db_file=DB_FILE):
    """Delete every registered dataset and all of its derived reports.

    Only TXT paths derived from the current registry rows are removed;
    unrelated files in ``reports/`` are never enumerated or removed.
    ``current_report.json`` is removed unconditionally because the
    requested clear operation leaves no valid dataset that it could
    represent.

    Returns the number of registered datasets that were targeted.
    """
    owns_registry = registry is None
    if owns_registry:
        registry = DatasetRegistry(db_file=db_file)
        registry.connect()

    datasets = registry.list_datasets()
    try:
        report_store.delete_current_json()
        for dataset in datasets:
            report_store.delete_txt_report(dataset)
        registry.clear_datasets()
    except Exception as exc:
        if isinstance(exc, DatasetLifecycleError):
            raise
        raise _lifecycle_error("Could not clear dataset history", exc) from exc
    return len(datasets)
