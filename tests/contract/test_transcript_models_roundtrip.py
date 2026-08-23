"""SC-005: every 002 contract model round-trips (T007)."""

from __future__ import annotations

import pytest

from ambient_recorder.models.session import utcnow
from ambient_recorder.models.transcript import (
    JobInfo,
    JobState,
    NewSegment,
    PendingJobInfo,
    ReadinessState,
    SegmentFrame,
    Speaker,
    StatusFrame,
    Transcript,
    TranscriptionJob,
    TranscriptionJobResponse,
    TranscriptionReadiness,
    TranscriptListResponse,
    TranscriptMode,
    TranscriptResponse,
    TranscriptSegment,
    TranscriptState,
    TranscriptSummary,
)

_SEG = TranscriptSegment(
    transcript_id="t", seq=3, source=Speaker.THEM, start_s=12.4, end_s=15.9, text="push the launch"
)

SAMPLES = [
    Transcript(session_id="s", mode=TranscriptMode.LIVE, state=TranscriptState.LIVE),
    _SEG,
    NewSegment(source=Speaker.ME, start_s=0.0, end_s=1.0, text="hi"),
    TranscriptionJob(
        transcript_id="t",
        session_id="s",
        mode=TranscriptMode.ON_DEMAND,
        state=JobState.QUEUED,
        priority=1,
        total_chunks=42,
    ),
    TranscriptionReadiness(
        status=ReadinessState.READY,
        ready=True,
        engine="faster-whisper",
        model="medium/int8_float16/cuda",
        device="cuda",
        free_vram_mb=7900,
        required_vram_mb=2200,
    ),
    TranscriptionReadiness(status=ReadinessState.NOT_INSTALLED, ready=False, reason="x"),
    TranscriptResponse(
        id="t",
        session_id="s",
        mode=TranscriptMode.LIVE,
        state=TranscriptState.LIVE,
        final=False,
        model=None,
        segments=[_SEG],
        job=JobInfo(state=JobState.RUNNING, lag_s=2.5),
        pending_job=PendingJobInfo(
            transcript_id="t2", state=JobState.RUNNING, progress_chunks=4, total_chunks=10
        ),
    ),
    TranscriptListResponse(
        transcripts=[
            TranscriptSummary(
                id="t",
                mode=TranscriptMode.LIVE,
                state=TranscriptState.COMPLETED,
                final=True,
                superseded=True,
                model="m",
                created_at=utcnow(),
                finalised_at=utcnow(),
                segment_count=7,
            )
        ]
    ),
    TranscriptionJobResponse(transcript_id="t", session_id="s", state=JobState.QUEUED),
    SegmentFrame(segment=_SEG),
    StatusFrame(state=TranscriptState.FINALISING, lag_s=8.0),
]


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda s: type(s).__name__)
def test_roundtrip_identity(sample):
    dumped = sample.model_dump(mode="json")
    assert type(sample).model_validate(dumped).model_dump(mode="json") == dumped


def test_segment_validation():
    with pytest.raises(ValueError):
        TranscriptSegment(transcript_id="t", seq=0, source=Speaker.ME, start_s=1, end_s=1, text="x")
    with pytest.raises(ValueError):
        TranscriptSegment(
            transcript_id="t", seq=0, source=Speaker.ME, start_s=0, end_s=1, text="  "
        )
