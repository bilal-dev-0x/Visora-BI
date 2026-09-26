"""Typed request/response contracts for the public API."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    code: str = Field(description="Machine-readable error code")
    message: str = Field(description="Human-readable, safe user message")
    detail: Optional[Any] = Field(default=None, description="Optional structured context")


class ErrorEnvelope(BaseModel):
    error: ErrorBody


class UploadResponse(BaseModel):
    dataset: dict[str, Any]
    warning: Optional[str] = None


class DeleteResponse(BaseModel):
    deleted: bool
    dataset_id: str
    removed_reports: int = 0


class ClearHistoryResponse(BaseModel):
    deleted_datasets: int
    deleted_reports: int


class AnalyzeResponse(BaseModel):
    report: dict[str, Any]
