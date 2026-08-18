"""Transcription domain + API models — normative per specs/002 data-model.md
and contracts/rest-api.md."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from ambient_recorder.models.session import new_ulid, utcnow


class TranscriptMode(StrEnum):
    LIVE = "live"
    ON_DEMAND = "on_demand"


class TranscriptState(StrEnum):
    PENDING = "pending"  # on-demand attempt queued/running; never "current"
    LIVE = "live"
    FINALISING = "finalising"
    COMPLETED = "completed"
    INTERRUPTED_LIVE = "interrupted_live"
    FAILED = "failed"


class JobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    FINALISING = "finalising"
    COMPLETED = "completed"
    FAILED = "failed"


class Speaker(StrEnum):
    ME = "me"  # microphone track
    THEM = "them"  # system-audio track


class ReadinessState(StrEnum):
    READY = "ready"
    NOT_READY = "not_ready"  # installed but unusable → live transcripts fail visibly
    NOT_INSTALLED = "not_installed"  # capture-only install → live mode skipped


# -- domain ---------------------------------------------------------------


class Transcript(BaseModel):
    id: str = Field(default_factory=new_ulid)
    session_id: str
    mode: TranscriptMode
    state: TranscriptState
    final: bool = False
    engine: str | None = None
    model: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    finalised_at: datetime | None = None
    failure_reason: str | None = None


class TranscriptSegment(BaseModel):
    transcript_id: str
    seq: int = Field(ge=0)  # store-assigned; the stream cursor
    source: Speaker
    start_s: float = Field(ge=0)
    end_s: float
    text: str

    @field_validator("text")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("segment text must be non-empty")
        return v

    @field_validator("end_s")
    @classmethod
    def _end_after_start(cls, v: float, info):
        start = info.data.get("start_s")
        if start is not None and v <= start:
            raise ValueError("end_s must be > start_s")
        return v


class NewSegment(BaseModel):
    """Segment before the store assigns seq."""

    source: Speaker
    start_s: float = Field(ge=0)
    end_s: float
    text: str


class TranscriptionJob(BaseModel):
    transcript_id: str
    session_id: str
    mode: TranscriptMode
    state: JobState
    priority: int = 0  # 0 live, 1 on-demand
    progress_chunks: int = 0
    total_chunks: int | None = None
    lag_s: float | None = None
    enqueued_at: datetime = Field(default_factory=utcnow)
    started_at: datetime | None = None
    ended_at: datetime | None = None
    failure_reason: str | None = None


# -- API ------------------------------------------------------------------


class TranscriptionReadiness(BaseModel):
    status: ReadinessState
    ready: bool
    engine: str | None = None
    model: str | None = None
    device: Literal["cuda", "cpu"] | None = None
    free_vram_mb: int | None = None
    required_vram_mb: int | None = None
    reason: str | None = None


class JobInfo(BaseModel):
    state: JobState
    lag_s: float | None = None
    progress_chunks: int = 0
    total_chunks: int | None = None
    failure_reason: str | None = None


class PendingJobInfo(BaseModel):
    transcript_id: str
    state: JobState
    progress_chunks: int = 0
    total_chunks: int | None = None


class TranscriptResponse(BaseModel):
    id: str
    session_id: str
    mode: TranscriptMode
    state: TranscriptState
    final: bool
    model: str | None
    segments: list[TranscriptSegment]
    job: JobInfo
    pending_job: PendingJobInfo | None = None


class TranscriptSummary(BaseModel):
    id: str
    mode: TranscriptMode
    state: TranscriptState
    final: bool
    superseded: bool
    model: str | None
    created_at: datetime
    finalised_at: datetime | None
    segment_count: int


class TranscriptListResponse(BaseModel):
    transcripts: list[TranscriptSummary]


class TranscriptionJobResponse(BaseModel):
    transcript_id: str
    session_id: str
    state: JobState


class SegmentFrame(BaseModel):
    type: Literal["segment"] = "segment"
    segment: TranscriptSegment


class StatusFrame(BaseModel):
    type: Literal["status"] = "status"
    state: TranscriptState
    lag_s: float | None = None
    final: bool = False
