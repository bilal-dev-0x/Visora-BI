"""FastAPI application exposing the existing VISORA BI backend.

Run with::

    uvicorn api.main:app --reload

The API is a thin transport adapter: every analytical decision stays in
``backend/`` (registry, ingestion, analysis_context, evidence,
prioritization, ai_service, pipeline, report_store).
"""

from __future__ import annotations

import shutil
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from api.errors import APIError, register_error_handlers
from api.schemas import (
    ClearHistoryResponse,
    DeleteResponse,
    ErrorEnvelope,
    UploadResponse,
)
from api.serializers import (
    build_dataset_profile,
    build_insights,
    build_overview,
    dataset_status,
    list_reports,
    serialize_dataset,
)
from backend import pipeline, report_store
from backend.config import (
    MAX_UPLOAD_SIZE_BYTES,
    MAX_UPLOAD_SIZE_MB,
    SUPPORTED_UPLOAD_EXTENSIONS,
)
from backend.dataset_registry import DatasetRegistry
from backend.ingestion import DatasetIngestor

# FastAPI runs sync endpoints on worker threads; SQLite writes are
# serialized here so a delete cannot race an analysis or an upload.
_MUTATION_LOCK = threading.Lock()

API_VERSION = "1.0.0"

app = FastAPI(
    title="VISORA BI API",
    version=API_VERSION,
    description=(
        "Transport layer for the VISORA BI Python backend. All analytics, "
        "evidence, prioritization, AI, and report logic live in backend/."
    ),
    responses={"422": {"model": ErrorEnvelope}},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_error_handlers(app)


def get_registry() -> DatasetRegistry:
    registry = DatasetRegistry()
    connection = registry.conn
    try:
        yield registry
    finally:
        try:
            connection.close()
        except Exception:  # pragma: no cover - defensive close
            pass


def get_ingestor() -> DatasetIngestor:
    ingestor = DatasetIngestor()
    connection = ingestor.conn
    try:
        yield ingestor
    finally:
        try:
            connection.close()
        except Exception:  # pragma: no cover - defensive close
            pass


def _require_dataset(registry: DatasetRegistry, dataset_id: str) -> dict:
    row = registry.get_dataset(dataset_id)
    if not row:
        raise APIError(404, "dataset_not_found", "That dataset no longer exists.")
    return row


# ---------------------------------------------------------------- system


@app.get("/api/v1/health", tags=["system"])
def health(registry: DatasetRegistry = Depends(get_registry)) -> dict:
    from backend.config import load_provider_chain

    rows = registry.list_datasets()
    providers = load_provider_chain()
    configured = [p for p in providers if p.is_configured]
    current = report_store.load_current_json()
    return {
        "status": "operational",
        "version": API_VERSION,
        "time": datetime.now(timezone.utc).isoformat(),
        "datasets": len(rows),
        "reports": len(list_reports(registry)["reports"]),
        "currentReport": bool(current),
        "uploadLimitBytes": MAX_UPLOAD_SIZE_BYTES,
        "uploadLimitMb": MAX_UPLOAD_SIZE_MB,
        "ai": {
            "mode": "provider_chain" if configured else "local_fallback",
            "configuredProviders": len(configured),
            "totalSlots": len(providers),
        },
    }


@app.get("/api/v1/overview", tags=["dashboard"])
def overview(registry: DatasetRegistry = Depends(get_registry)) -> dict:
    return build_overview(registry)


# ---------------------------------------------------------------- datasets


@app.get("/api/v1/datasets", tags=["datasets"])
def datasets(registry: DatasetRegistry = Depends(get_registry)) -> dict:
    rows = registry.list_datasets()
    return {"datasets": [serialize_dataset(r) for r in rows]}


@app.post(
    "/api/v1/datasets",
    response_model=UploadResponse,
    tags=["datasets"],
    summary="Register and ingest a CSV upload",
)
def upload_dataset(
    file: UploadFile = File(...),
    registry: DatasetRegistry = Depends(get_registry),
    ingestor: DatasetIngestor = Depends(get_ingestor),
) -> dict:
    filename = (file.filename or "").strip()
    extension = Path(filename).suffix.lower().lstrip(".")
    if extension not in SUPPORTED_UPLOAD_EXTENSIONS:
        supported = ", ".join(f".{name}" for name in SUPPORTED_UPLOAD_EXTENSIONS)
        raise APIError(
            400,
            "unsupported_file_type",
            f"VISORA accepts {supported} files right now. Please upload a supported file.",
        )

    suffix = Path(filename).suffix
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        size = 0
        while True:
            chunk = file.file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_UPLOAD_SIZE_BYTES:
                raise APIError(
                    413,
                    "file_too_large",
                    f"'{filename}' exceeds the {MAX_UPLOAD_SIZE_MB} MB upload limit.",
                )
            tmp.write(chunk)
        tmp.close()
        if size == 0:
            raise APIError(400, "empty_file", "That file is empty.")

        with _MUTATION_LOCK:
            try:
                dataset_id = registry.register_upload(filename, Path(tmp.name))
            except Exception as exc:
                raise APIError(
                    500,
                    "upload_failed",
                    "VISORA could not save that file. Please try again.",
                    detail=str(exc),
                ) from exc

            try:
                row = registry.get_dataset(dataset_id)
                table = row.get("table_name")
                ingest_result = ingestor.ingest_csv(tmp.name, table)
            except Exception as exc:
                pipeline.delete_dataset_and_report(dataset_id, registry=registry)
                raise APIError(
                    500,
                    "ingest_failed",
                    "VISORA could not read that CSV. Please check the file and retry.",
                    detail=str(exc),
                ) from exc

            if ingest_result.get("ingested"):
                registry.update_counts(
                    dataset_id,
                    int(ingest_result.get("row_count") or 0),
                    int(ingest_result.get("column_count") or 0),
                )
            else:
                registry.update_counts(dataset_id, 0, 0)

            row = registry.get_dataset(dataset_id)
            payload = serialize_dataset(row)
            warning = None if ingest_result.get("ingested") else ingest_result.get("reason")
            return {"dataset": payload, "warning": warning}
    finally:
        try:
            tmp.close()
        except Exception:
            pass
        try:
            Path(tmp.name).unlink(missing_ok=True)
        except OSError:
            pass


@app.get("/api/v1/datasets/{dataset_id}", tags=["datasets"])
def dataset_detail(dataset_id: str, registry: DatasetRegistry = Depends(get_registry)) -> dict:
    row = _require_dataset(registry, dataset_id)
    profile = build_dataset_profile(row)
    current = report_store.load_current_json() or {}
    is_current = (current.get("dataset") or {}).get("dataset_id") == dataset_id
    return {
        "dataset": serialize_dataset(row),
        "profile": profile,
        "status": dataset_status(row),
        "isCurrentAnalysis": is_current,
        "currentReport": current if is_current else None,
    }


@app.delete("/api/v1/datasets/{dataset_id}", response_model=DeleteResponse, tags=["datasets"])
def delete_dataset(dataset_id: str, registry: DatasetRegistry = Depends(get_registry)) -> dict:
    with _MUTATION_LOCK:
        row = registry.get_dataset(dataset_id)
        if not row:
            raise APIError(404, "dataset_not_found", "That dataset no longer exists.")
        txt_exists = bool(report_store.txt_report_exists(row))
        current = report_store.load_current_json() or {}
        current_owned = (current.get("dataset") or {}).get("dataset_id") == dataset_id
        removed = pipeline.delete_dataset_and_report(dataset_id, registry=registry)
        if removed is None:
            raise APIError(404, "dataset_not_found", "That dataset no longer exists.")
        return {
            "deleted": True,
            "dataset_id": dataset_id,
            "removed_reports": int(txt_exists) + int(current_owned),
        }


@app.post(
    "/api/v1/datasets/{dataset_id}/analyze",
    tags=["datasets"],
    summary="Run the unified analysis pipeline for a dataset",
)
def analyze_dataset(dataset_id: str, registry: DatasetRegistry = Depends(get_registry)) -> dict:
    _require_dataset(registry, dataset_id)
    with _MUTATION_LOCK:
        report = pipeline.analyze_dataset(dataset_id, registry=registry)
    return {"report": report}


# ---------------------------------------------------------------- reports


@app.get("/api/v1/reports", tags=["reports"])
def reports(registry: DatasetRegistry = Depends(get_registry)) -> dict:
    return list_reports(registry)


@app.get("/api/v1/reports/current", tags=["reports"])
def current_report() -> dict:
    report = report_store.load_current_json()
    if not report:
        raise APIError(404, "no_current_report", "No analysis has been run yet.")
    return report


@app.get("/api/v1/reports/{dataset_id}/text", tags=["reports"])
def download_text_report(dataset_id: str, registry: DatasetRegistry = Depends(get_registry)) -> FileResponse:
    row = _require_dataset(registry, dataset_id)
    try:
        path = report_store.txt_report_path(row)
    except Exception:
        path = None
    if not path or not Path(path).exists():
        raise APIError(
            404,
            "report_not_found",
            "No report exists for that dataset yet. Run an analysis first.",
        )
    return FileResponse(
        path,
        media_type="text/plain; charset=utf-8",
        filename=Path(path).name,
    )


@app.post(
    "/api/v1/history/clear",
    response_model=ClearHistoryResponse,
    tags=["reports"],
)
def clear_history(registry: DatasetRegistry = Depends(get_registry)) -> dict:
    with _MUTATION_LOCK:
        rows = registry.list_datasets()
        txt_count = sum(1 for row in rows if report_store.txt_report_exists(row))
        has_current = report_store.load_current_json() is not None
        pipeline.clear_datasets_and_reports(registry=registry)
        return {
            "deleted_datasets": len(rows),
            "deleted_reports": txt_count + int(has_current),
        }


# ---------------------------------------------------------------- insights


@app.get("/api/v1/insights", tags=["insights"])
def insights(registry: DatasetRegistry = Depends(get_registry)) -> dict:
    return build_insights(registry)
