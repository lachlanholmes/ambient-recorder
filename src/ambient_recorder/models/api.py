"""API payload models — normative contracts per specs/001 contracts/rest-api.md."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from ambient_recorder.models.session import (
    SessionEvent,
    SessionStatus,
    SourceKind,
    SourceStatus,
)


class ErrorCode(StrEnum):
    DEVICE_MISSING = "device_missing"
    SESSION_ALREADY_ACTIVE = "session_already_active"
    SESSION_NOT_FOUND = "session_not_found"
    SESSION_NOT_ACTIVE = "session_not_active"
    DISK_SPACE_LOW = "disk_space_low"
    VALIDATION_ERROR = "validation_error"
    INTERNAL_ERROR = "internal_error"


class ErrorBody(BaseModel):
    code: ErrorCode
    message: str
    detail: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorBody


class SessionCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class SessionSummary(BaseModel):
    id: str
    title: str | None
    status: SessionStatus
    started_at: datetime
    ended_at: datetime | None
    duration_s: float | None
    size_bytes: int


class CaptureSourceInfo(BaseModel):
    kind: SourceKind
    device_id: str
    device_label: str
    native_rate_hz: int
    persisted_format: str
    status: SourceStatus
    ended_at: datetime | None
    chunk_count: int


class SessionDetail(SessionSummary):
    sources: list[CaptureSourceInfo]
    events: list[SessionEvent]
    chunk_counts: dict[SourceKind, int]


class SessionListResponse(BaseModel):
    sessions: list[SessionSummary]


class ReadinessStatus(StrEnum):
    PRESENT = "present"
    MISSING = "missing"
    DEFAULT_CHANGED = "default_changed"


class DeviceReadiness(BaseModel):
    kind: SourceKind
    status: ReadinessStatus
    device_id: str | None = None
    device_label: str | None = None


class DeviceReadinessResponse(BaseModel):
    sources: list[DeviceReadiness]
    ready: bool


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    active_session_id: str | None = None
