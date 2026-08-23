"""T032: restart mid-live → interrupted_live (segments kept); restart mid
on-demand → requeued and completes."""

from __future__ import annotations

from fastapi.testclient import TestClient
from tests.conftest import wait_until
from tests.support.fake_capture import MIC_ID, SYSTEM_ID
from tests.support.fake_speech import seg

from ambient_recorder.main import create_app


def test_orphaned_live_becomes_interrupted_live(
    settings, fake_provider, enumerator, fake_engine, engine_factory
):
    fake_engine.script[("mic", 0)] = [seg(1.0, 2.0, "survivor")]
    # Boot 1: start a session, get one segment, then "crash" (drop the app
    # without stopping the session — mirrors kill -9).
    app1 = create_app(settings, fake_provider, enumerator, engine_factory)
    with TestClient(app1) as c1:
        sid = c1.post("/sessions", json={}).json()["id"]
        fake_provider.push_seconds(MIC_ID, 10.0)
        fake_provider.push_seconds(SYSTEM_ID, 10.0)
        assert wait_until(
            lambda: len(c1.get(f"/sessions/{sid}/transcript").json()["segments"]) == 1
        )
    # Boot 2: feature 001 reconciles the session; 002 reconciles the transcript.
    with TestClient(create_app(settings, fake_provider, enumerator, engine_factory)) as c2:
        assert c2.get(f"/sessions/{sid}").json()["status"] == "interrupted"
        t = c2.get(f"/sessions/{sid}/transcript").json()
        assert t["state"] == "interrupted_live" and t["final"] is False
        assert [s["text"] for s in t["segments"]] == ["survivor"]  # kept
        # Backfill works from here.
        assert c2.post(f"/sessions/{sid}/transcribe").status_code == 202
        assert wait_until(
            lambda: c2.get(f"/sessions/{sid}/transcript").json()["mode"] == "on_demand"
        )


def test_orphaned_on_demand_is_requeued(
    settings, fake_provider, enumerator, fake_engine, engine_factory
):
    fake_engine.script[("mic", 0)] = [seg(1.0, 2.0, "eventually")]
    with TestClient(create_app(settings, fake_provider, enumerator, engine_factory)) as c1:
        sid = c1.post("/sessions", json={}).json()["id"]
        fake_provider.push_seconds(MIC_ID, 60.0)  # 6 chunks/track → a real mid-flight window
        fake_provider.push_seconds(SYSTEM_ID, 60.0)
        assert wait_until(lambda: c1.get(f"/sessions/{sid}").json()["chunk_counts"]["mic"] >= 6)
        c1.post(f"/sessions/{sid}/stop")
        assert wait_until(
            lambda: c1.get(f"/sessions/{sid}/transcript").json()["state"] == "completed"
        )
        # The on-demand run re-reads the chunks; the fake's per-track call index
        # continues (live used mic idx 0–5), so script the dead run's first mic
        # window (idx 6) to emit one segment, then make everything slow.
        fake_engine.script[("mic", 6)] = [seg(1.0, 2.0, "eventually")]
        fake_engine.delay_s = 0.3
        od = c1.post(f"/sessions/{sid}/transcribe").json()["transcript_id"]
        assert wait_until(
            lambda: len(c1.get(f"/sessions/{sid}/transcripts/{od}").json()["segments"]) >= 1
        )
        fake_engine.delay_s = 10.0  # job is now mid-flight when we "crash"
    fake_engine.delay_s = 0.0
    # The rerun re-reads from chunk 0: script the same segment on its first mic
    # window so the content is identical to the dead run's.
    fake_engine.script[("mic", fake_engine._counts["mic"])] = [seg(1.0, 2.0, "eventually")]
    with TestClient(create_app(settings, fake_provider, enumerator, engine_factory)) as c2:
        assert wait_until(
            lambda: c2.get(f"/sessions/{sid}/transcripts/{od}").json()["state"] == "completed",
            timeout_s=15,
        )
        # FR-006 retry-from-scratch: the dead run's segment must NOT survive
        # alongside the rerun's — exactly one copy (field: 69-min requeued job
        # produced every segment in duplicate before this was fixed).
        segs = c2.get(f"/sessions/{sid}/transcripts/{od}").json()["segments"]
        assert [s["text"] for s in segs].count("eventually") == 1, segs
