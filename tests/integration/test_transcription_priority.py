"""T034: live work (priority 0) interleaves ahead of on-demand (priority 1);
session start under contention stays within the CI ceiling."""

from __future__ import annotations

import time

from tests.conftest import wait_until
from tests.support.fake_capture import MIC_ID, SYSTEM_ID


def test_live_preempts_on_demand(client, fake_provider, fake_engine):
    # A completed session with many chunks to backfill slowly.
    sid_old = client.post("/sessions", json={}).json()["id"]
    fake_provider.push_seconds(MIC_ID, 60.0)
    fake_provider.push_seconds(SYSTEM_ID, 60.0)
    assert wait_until(lambda: client.get(f"/sessions/{sid_old}").json()["chunk_counts"]["mic"] >= 6)
    client.post(f"/sessions/{sid_old}/stop")
    assert wait_until(
        lambda: client.get(f"/sessions/{sid_old}/transcript").json()["state"] == "completed"
    )

    fake_engine.delay_s = 0.2
    fake_engine.calls.clear()
    client.post(f"/sessions/{sid_old}/transcribe")
    assert wait_until(lambda: len(fake_engine.calls) >= 1)

    # New session starts fast despite the busy worker (FR-008).
    t0 = time.monotonic()
    r = client.post("/sessions", json={"title": "contention"})
    assert r.status_code == 201 and time.monotonic() - t0 < 5.0
    sid_new = r.json()["id"]
    n_before = len(fake_engine.modes)
    fake_provider.push_seconds(MIC_ID, 10.0)
    fake_provider.push_seconds(SYSTEM_ID, 10.0)
    # Once the two live chunks are queued (priority 0), they must be served
    # before any further on-demand step (priority 1). Allow one in-flight
    # on-demand call that had already been dequeued when they arrived.
    assert wait_until(lambda: fake_engine.modes[n_before:].count("live") >= 2)
    window = fake_engine.modes[n_before:]
    first_two_live = [i for i, m in enumerate(window) if m == "live"][:2]
    assert first_two_live[-1] <= 2, window  # both live calls within the first 3 slots
    client.post(f"/sessions/{sid_new}/stop")
    fake_engine.delay_s = 0.0
