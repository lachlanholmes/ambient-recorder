"""US4: warm-process sessions start repeatedly, promptly, cleanly (T030, T031)."""

from __future__ import annotations

import time

from tests.support.fake_capture import MIC_ID


def test_five_sequential_sessions_no_leakage(client, fake_provider):
    ids = []
    for i in range(5):
        r = client.post("/sessions", json={"title": f"session {i}"})
        assert r.status_code == 201, r.text
        sid = r.json()["id"]
        fake_provider.push_seconds(MIC_ID, 1.0)
        assert client.post(f"/sessions/{sid}/stop").json()["status"] == "completed"
        ids.append(sid)

    listed = client.get("/sessions").json()["sessions"]
    assert [s["id"] for s in listed] == list(reversed(ids))
    assert all(s["status"] == "completed" for s in listed)
    assert client.get("/health").json()["active_session_id"] is None


def test_start_latency_within_generous_ci_ceiling(client, app):
    # SC-004's strict 2 s check is manual (T032); CI asserts a
    # flake-resistant ceiling only, per analyze finding A1.
    t0 = time.monotonic()
    r = client.post("/sessions", json={})
    elapsed = time.monotonic() - t0
    assert r.status_code == 201
    assert elapsed < 5.0
    sid = r.json()["id"]
    client.post(f"/sessions/{sid}/stop")
