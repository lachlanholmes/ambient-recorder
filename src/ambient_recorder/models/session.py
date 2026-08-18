"""Domain models — normative contracts per specs/001 data-model.md."""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator

# NFR-002: the persisted artifact format is fixed by spec.
PERSISTED_SAMPLE_RATE = 16_000
PERSISTED_CHANNELS = 1
PERSISTED_SAMPLE_WIDTH = 2  # bytes (s16le)
PERSISTED_FORMAT = "16000 Hz, mono, s16le"

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_ulid(now_ms: int | None = None) -> str:
    """26-char Crockford-base32 ULID: 48-bit ms timestamp + 80 random bits."""
    ts = int(time.time() * 1000) if now_ms is None else now_ms
    value = (ts << 80) | int.from_bytes(os.urandom(10))
    chars = []
    for _ in range(26):
        chars.append(_CROCKFORD[value & 0x1F])
        value >>= 5
    return "".join(reversed(chars))


def utcnow() -> datetime:
    return datetime.now(UTC)


class SourceKind(StrEnum):
    MIC = "mic"
    SYSTEM = "system"


class SessionStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"


class SourceStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ENDED_DEVICE_LOST = "ended_device_lost"


class EventType(StrEnum):
    STARTED = "started"
    STOPPED = "stopped"
    DEVICE_LOST = "device_lost"
    DEFAULT_OUTPUT_CHANGED = "default_output_changed"
    DISK_LOW = "disk_low"
    RECONCILED = "reconciled"


class Session(BaseModel):
    id: str = Field(default_factory=new_ulid)
    title: str | None = None
    status: SessionStatus = SessionStatus.ACTIVE
    started_at: datetime
    ended_at: datetime | None = None
    duration_s: float | None = None  # derived from audio length, never wall clock
    size_bytes: int = 0
    dir_path: str
    created_at: datetime = Field(default_factory=utcnow)

    @field_validator("title")
    @classmethod
    def _strip_title(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if len(v) > 200:
            raise ValueError("title must be at most 200 characters")
        return v or None


class CaptureSource(BaseModel):
    session_id: str
    kind: SourceKind
    device_id: str
    device_label: str
    native_rate_hz: int = Field(gt=0)
    persisted_format: str = PERSISTED_FORMAT
    status: SourceStatus = SourceStatus.ACTIVE
    ended_at: datetime | None = None
    chunk_count: int = 0


class AudioChunk(BaseModel):
    session_id: str
    source_kind: SourceKind
    seq: int = Field(ge=0)
    file_path: str
    duration_s: float = Field(gt=0, le=10.0)
    size_bytes: int = Field(gt=44)  # must exceed a bare WAV header
    written_at: datetime = Field(default_factory=utcnow)


class SessionEvent(BaseModel):
    session_id: str
    at: datetime = Field(default_factory=utcnow)
    type: EventType
    detail: dict[str, Any] = Field(default_factory=dict)
