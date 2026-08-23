"""T008: observer hooks fire and can never hurt capture (constitution VII)."""

from __future__ import annotations

from tests.conftest import wait_until
from tests.support.fake_capture import MIC_ID, SYSTEM_ID


def test_chunk_and_session_observers_fire(app, client, fake_provider):
    engine = app.state.engine
    chunks, events = [], []
    engine.add_chunk_observer(lambda sid, kind, meta: chunks.append((sid, kind, meta.seq)))
    engine.add_session_observer(lambda sid, ev: events.append((sid, ev)))

    sid = client.post("/sessions", json={}).json()["id"]
    fake_provider.push_seconds(MIC_ID, 21.0)
    assert wait_until(lambda: len(chunks) >= 2)
    client.post(f"/sessions/{sid}/stop")

    assert [c[2] for c in chunks if c[1] == "mic"][:2] == [0, 1]
    assert [e[1] for e in events] == ["started", "stopped", "finalized"]
    assert all(e[0] == sid for e in events)


def test_raising_observer_does_not_affect_capture(app, client, fake_provider):
    engine = app.state.engine

    def boom(*_):
        raise RuntimeError("observer exploded")

    engine.add_chunk_observer(boom)
    engine.add_session_observer(boom)

    sid = client.post("/sessions", json={}).json()["id"]  # started observer raised
    fake_provider.push_seconds(MIC_ID, 12.0)
    assert wait_until(lambda: client.get(f"/sessions/{sid}").json()["chunk_counts"]["mic"] >= 1)
    detail = client.post(f"/sessions/{sid}/stop").json()
    assert detail["status"] == "completed"
    assert detail["chunk_counts"]["mic"] == 2  # 10 s chunk + 2 s flush, nothing lost


def test_silence_gap_is_zero_filled_so_tracks_share_a_clock(app, client, fake_provider):
    """Loopback delivers no frames during output silence; the writer must
    pad the gap so chunk seq x 10 s stays true session time on every track."""
    import time

    from ambient_recorder.audio import engine as eng

    fake_provider.realtime = True  # opt into wall-clock gap semantics
    sid = client.post("/sessions", json={}).json()["id"]
    fake_provider.push_seconds(SYSTEM_ID, 2.0)  # 2 s of audio, then silence...
    time.sleep(eng._GAP_FILL_THRESHOLD_S + 0.7)  # ...for ~1.2 s of wall clock
    fake_provider.push_seconds(SYSTEM_ID, 9.0)  # audio resumes
    assert wait_until(lambda: client.get(f"/sessions/{sid}").json()["chunk_counts"]["system"] >= 1)
    detail = client.post(f"/sessions/{sid}/stop").json()
    # 2 s + ~1.2 s gap + 9 s ≈ 12.2 s of system-track time → 2 chunks, not 1
    assert detail["chunk_counts"]["system"] == 2
    assert detail["duration_s"] >= 12.0
