"""Storage-side Protocols — normative contracts per specs/001 contracts/protocols.md."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel

from ambient_recorder.models.api import SessionDetail, SessionSummary
from ambient_recorder.models.session import (
    AudioChunk,
    CaptureSource,
    Session,
    SessionEvent,
    SourceKind,
)


class ChunkMeta(BaseModel):
    file_path: str
    seq: int
    duration_s: float
    size_bytes: int


class DiskFullError(Exception):
    pass


class ActiveSessionExistsError(Exception):
    def __init__(self, active_id: str):
        self.active_id = active_id
        super().__init__(f"a session is already active: {active_id}")


@runtime_checkable
class ChunkStore(Protocol):
    def write_chunk(
        self, session_id: str, kind: SourceKind, seq: int, pcm16k_mono: bytes
    ) -> ChunkMeta: ...

    def inventory(self, session_id: str, kind: SourceKind) -> list[ChunkMeta]: ...


@runtime_checkable
class MetadataStore(Protocol):
    def create_active_session(
        self, session: Session, sources: list[CaptureSource]
    ) -> None: ...

    def record_chunk(self, chunk: AudioChunk) -> None: ...

    def end_source(
        self,
        session_id: str,
        kind: SourceKind,
        status: Literal["completed", "ended_device_lost"],
        ended_at: datetime,
    ) -> None: ...

    def append_event(self, event: SessionEvent) -> None: ...

    def finalize_session(
        self,
        session_id: str,
        status: Literal["completed", "interrupted"],
        ended_at: datetime,
        duration_s: float,
    ) -> None: ...

    def list_sessions(self) -> list[SessionSummary]: ...

    def get_session(self, session_id: str) -> SessionDetail | None: ...

    def active_sessions(self) -> list[Session]: ...

    def last_device_ids(self) -> dict[SourceKind, str]: ...
