"""SC-005: every contract model round-trips through its JSON schema."""

from __future__ import annotations

import pytest

from ambient_recorder.models.api import (
    CaptureSourceInfo,
    DeviceReadiness,
    DeviceReadinessResponse,
    ErrorBody,
    ErrorCode,
    ErrorResponse,
    HealthResponse,
    ReadinessStatus,
    SessionCreateRequest,
    SessionDetail,
    SessionListResponse,
    SessionSummary,
)
from ambient_recorder.models.session import (
    AudioChunk,
    CaptureSource,
    EventType,
    Session,
    SessionEvent,
    SourceKind,
    new_ulid,
    utcnow,
)

_SUMMARY = dict(id=new_ulid(), title="t", status="active", started_at=utcnow(),
                ended_at=None, duration_s=None, size_bytes=0)
_SOURCE_INFO = CaptureSourceInfo(
    kind=SourceKind.MIC, device_id="d", device_label="D", native_rate_hz=48000,
    persisted_format="16000 Hz, mono, s16le", status="active", ended_at=None,
    chunk_count=0)

SAMPLES = [
    Session(title="Weekly sync", started_at=utcnow(), dir_path="data/sessions/x"),
    CaptureSource(session_id="s", kind=SourceKind.SYSTEM, device_id="d",
                  device_label="Speakers", native_rate_hz=48000),
    AudioChunk(session_id="s", source_kind=SourceKind.MIC, seq=0,
               file_path="p/chunk_000000.wav", duration_s=10.0, size_bytes=320044),
    SessionEvent(session_id="s", type=EventType.DEVICE_LOST,
                 detail={"kind": "mic", "last_seq": 3}),
    SessionCreateRequest(title="hello"),
    SessionSummary(**_SUMMARY),
    SessionDetail(**_SUMMARY, sources=[_SOURCE_INFO],
                  events=[SessionEvent(session_id="s", type=EventType.STARTED)],
                  chunk_counts={SourceKind.MIC: 1, SourceKind.SYSTEM: 2}),
    SessionListResponse(sessions=[SessionSummary(**_SUMMARY)]),
    DeviceReadiness(kind=SourceKind.MIC, status=ReadinessStatus.MISSING),
    DeviceReadinessResponse(sources=[], ready=False),
    ErrorResponse(error=ErrorBody(code=ErrorCode.DEVICE_MISSING, message="m",
                                  detail={"missing": ["mic"]})),
    HealthResponse(version="0.1.0"),
]


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda s: type(s).__name__)
def test_roundtrip_identity(sample):
    model_cls = type(sample)
    dumped = sample.model_dump(mode="json")
    assert model_cls.model_validate(dumped).model_dump(mode="json") == dumped


def test_title_validation_limits():
    with pytest.raises(ValueError):
        Session(title="x" * 201, started_at=utcnow(), dir_path="d")
    assert Session(title="  padded  ", started_at=utcnow(), dir_path="d").title == "padded"
