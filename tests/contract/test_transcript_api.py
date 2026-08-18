"""T014/T025: transcript REST contracts."""

from __future__ import annotations

from tests.conftest import wait_until
from tests.support.fake_capture import MIC_ID, SYSTEM_ID
from tests.support.fake_speech import seg

from ambient_recorder.models.api import ErrorCode
from ambient_recorder.models.transcript import TranscriptListResponse, TranscriptResponse


def test_transcript_404s(client):
    assert client.get("/sessions/nope/transcript").status_code == 404
    assert client.get("/sessions/nope/transcripts").status_code == 404
    r = client.get("/sessions/nope/transcripts/whatever")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == ErrorCode.TRANSCRIPT_NOT_FOUND


def test_transcript_shape_and_ordering(client, fake_provider, fake_engine):
    fake_engine.script[("mic", 0)] = [seg(5.0, 6.0, "second")]
    fake_engine.script[("system", 0)] = [seg(1.0, 2.0, "first")]
    sid = client.post("/sessions", json={}).json()["id"]
    fake_provider.push_seconds(MIC_ID, 10.0)
    fake_provider.push_seconds(SYSTEM_ID, 10.0)
    assert wait_until(
        lambda: len(client.get(f"/sessions/{sid}/transcript").json()["segments"]) == 2
    )
    body = TranscriptResponse.model_validate(client.get(f"/sessions/{sid}/transcript").json())
    assert [s.text for s in body.segments] == ["first", "second"]  # by start_s, not seq
    assert body.job.state == "running" and body.job.lag_s is not None
    assert body.pending_job is None

    listed = TranscriptListResponse.model_validate(
        client.get(f"/sessions/{sid}/transcripts").json()
    )
    assert len(listed.transcripts) == 1 and listed.transcripts[0].segment_count == 2
    by_id = client.get(f"/sessions/{sid}/transcripts/{body.id}")
    assert by_id.status_code == 200 and by_id.json()["id"] == body.id
    client.post(f"/sessions/{sid}/stop")


def test_readiness_endpoint(client):
    r = client.get("/transcription/readiness").json()
    assert r["status"] == "ready" and r["ready"] is True and r["engine"] == "fake-engine"
