"""Transcription Protocols — normative per specs/002 contracts/protocols.md.

Implementations: transcription/whisper_engine.py (real, gate c),
tests/support/fake_speech.py (scripted), storage/transcripts.py (store).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from ambient_recorder.models.session import SourceKind
from ambient_recorder.models.transcript import (
    NewSegment,
    Transcript,
    TranscriptionJob,
    TranscriptionReadiness,
    TranscriptSegment,
    TranscriptState,
    TranscriptSummary,
)
from ambient_recorder.storage.protocols import ChunkMeta


class RawSegment(BaseModel):
    """Engine output relative to the audio buffer passed in."""

    start_s: float
    end_s: float
    text: str
    avg_logprob: float | None = None


class EngineError(Exception):
    pass


class EngineNotReadyError(Exception):
    def __init__(self, readiness: TranscriptionReadiness):
        self.readiness = readiness
        super().__init__(readiness.reason or readiness.status.value)


@runtime_checkable
class SpeechEngine(Protocol):
    @property
    def descriptor(self) -> str: ...

    def transcribe(
        self,
        pcm16k_mono: bytes,
        *,
        beam_size: int = 1,
        initial_prompt: str | None = None,
    ) -> list[RawSegment]: ...


@runtime_checkable
class EngineFactory(Protocol):
    def readiness(self) -> TranscriptionReadiness: ...

    def load(self) -> SpeechEngine: ...


@runtime_checkable
class TranscriptStore(Protocol):
    def create_transcript(self, t: Transcript, job: TranscriptionJob) -> None: ...

    def append_segment(self, transcript_id: str, seg: NewSegment) -> TranscriptSegment: ...

    def update_job(self, transcript_id: str, **fields) -> None: ...

    def set_state(
        self,
        transcript_id: str,
        state: TranscriptState,
        *,
        final: bool = False,
        failure_reason: str | None = None,
        finalised_at: datetime | None = None,
    ) -> None: ...

    def current_transcript(self, session_id: str) -> Transcript | None: ...

    def pending_transcript(self, session_id: str) -> Transcript | None: ...

    def list_transcripts(self, session_id: str) -> list[TranscriptSummary]: ...

    def get_transcript(self, transcript_id: str) -> Transcript | None: ...

    def get_job(self, transcript_id: str) -> TranscriptionJob | None: ...

    def segments_after(self, transcript_id: str, after: int) -> list[TranscriptSegment]: ...

    def open_jobs(self) -> list[TranscriptionJob]: ...

    def next_queued(self) -> TranscriptionJob | None: ...


# Observers exposed by feature 001's CaptureEngine (contracts/protocols.md).
ChunkObserver = Callable[[str, SourceKind, ChunkMeta], None]
# event ∈ {"started", "stopped", "finalized"}
SessionObserver = Callable[[str, str], None]
