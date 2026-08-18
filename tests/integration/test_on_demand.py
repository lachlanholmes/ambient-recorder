"""T031: on-demand backfill, supersede-but-keep, pending never displaces, retry."""

from __future__ import annotations

from fastapi.testclient import TestClient
from tests.conftest import wait_until
from tests.support.fake_capture import MIC_ID, SYSTEM_ID
from tests.support.fake_speech import FakeEngineFactory, seg

from ambient_recorder.main import create_app
from ambient_recorder.models.transcript import ReadinessState


def _record_legacy_session(settings, fake_provider, enumerator) -> str:
    """A session recorded with transcription NOT installed → no transcript."""
    factory = FakeEngineFactory(status=ReadinessState.NOT_INSTALLED)
    with TestClient(create_app(settings, fake_provider, enumerator, factory)) as c:
        sid = c.post("/sessions", json={"title": "legacy"}).json()["id"]
        fake_provider.push_seconds(MIC_ID, 20.0)
        fake_provider.push_seconds(SYSTEM_ID, 20.0)
        assert wait_until(lambda: c.get(f"/sessions/{sid}").json()["chunk_counts"]["mic"] >= 2)
        c.post(f"/sessions/{sid}/stop")
    return sid


def test_legacy_session_backfilled(
    settings, fake_provider, enumerator, fake_engine, engine_factory
):
    sid = _record_legacy_session(settings, fake_provider, enumerator)
    fake_engine.script[("mic", 0)] = [seg(1.0, 2.0, "old meeting")]
    fake_engine.script[("system", 1)] = [seg(6.0, 7.0, "recovered")]  # session 11–12
    with TestClient(create_app(settings, fake_provider, enumerator, engine_factory)) as client:
        assert client.get(f"/sessions/{sid}/transcript").status_code == 404
        r = client.post(f"/sessions/{sid}/transcribe")
        assert r.status_code == 202
        tid = r.json()["transcript_id"]
        assert wait_until(
            lambda: client.get(f"/sessions/{sid}/transcript").json()["state"] == "completed"
        )
        t = client.get(f"/sessions/{sid}/transcript").json()
        assert t["id"] == tid and t["mode"] == "on_demand" and t["final"] is True
        assert t["job"]["progress_chunks"] == t["job"]["total_chunks"] == 4
        assert {s["text"] for s in t["segments"]} == {"old meeting", "recovered"}
        assert t["model"] == "fake-engine test/none/cpu"


def test_supersede_keeps_live_and_pending_never_displaces(client, fake_provider, fake_engine):
    fake_engine.script[("mic", 0)] = [seg(1.0, 2.0, "live words")]
    sid = client.post("/sessions", json={}).json()["id"]
    fake_provider.push_seconds(MIC_ID, 10.0)
    fake_provider.push_seconds(SYSTEM_ID, 10.0)
    assert wait_until(
        lambda: len(client.get(f"/sessions/{sid}/transcript").json()["segments"]) == 1
    )
    client.post(f"/sessions/{sid}/stop")
    assert wait_until(
        lambda: client.get(f"/sessions/{sid}/transcript").json()["state"] == "completed"
    )
    live_id = client.get(f"/sessions/{sid}/transcript").json()["id"]

    # Slow the engine so we can observe the pending state.
    fake_engine.delay_s = 0.15
    fake_engine.script[("mic", 1)] = [seg(1.0, 2.0, "on-demand words")]  # call idx continues
    r = client.post(f"/sessions/{sid}/transcribe")
    assert r.status_code == 202
    od_id = r.json()["transcript_id"]
    during = client.get(f"/sessions/{sid}/transcript").json()
    assert during["id"] == live_id  # still current while pending
    assert during["pending_job"]["transcript_id"] == od_id
    assert client.post(f"/sessions/{sid}/transcribe").status_code == 409  # already running

    assert wait_until(lambda: client.get(f"/sessions/{sid}/transcript").json()["id"] == od_id)
    listed = client.get(f"/sessions/{sid}/transcripts").json()["transcripts"]
    by_id = {x["id"]: x for x in listed}
    assert by_id[live_id]["superseded"] is True and by_id[od_id]["superseded"] is False
    old = client.get(f"/sessions/{sid}/transcripts/{live_id}").json()
    assert [s["text"] for s in old["segments"]] == ["live words"]  # kept, readable


def test_failed_on_demand_keeps_live_current_and_is_retryable(client, fake_provider, fake_engine):
    sid = client.post("/sessions", json={}).json()["id"]
    fake_provider.push_seconds(MIC_ID, 10.0)
    fake_provider.push_seconds(SYSTEM_ID, 10.0)
    client.post(f"/sessions/{sid}/stop")
    assert wait_until(
        lambda: client.get(f"/sessions/{sid}/transcript").json()["state"] == "completed"
    )
    live_id = client.get(f"/sessions/{sid}/transcript").json()["id"]

    fake_engine.fail_after_calls = len(fake_engine.calls)  # next call fails
    bad = client.post(f"/sessions/{sid}/transcribe").json()["transcript_id"]
    assert wait_until(
        lambda: client.get(f"/sessions/{sid}/transcripts/{bad}").json()["state"] == "failed"
    )
    assert client.get(f"/sessions/{sid}/transcript").json()["id"] == live_id  # live still current

    fake_engine.fail_after_calls = None
    good = client.post(f"/sessions/{sid}/transcribe").json()["transcript_id"]
    assert wait_until(lambda: client.get(f"/sessions/{sid}/transcript").json()["id"] == good)


def test_transcribe_refused_while_active(client):
    sid = client.post("/sessions", json={}).json()["id"]
    r = client.post(f"/sessions/{sid}/transcribe")
    assert r.status_code == 409 and r.json()["error"]["code"] == "session_still_active"
    client.post(f"/sessions/{sid}/stop")
