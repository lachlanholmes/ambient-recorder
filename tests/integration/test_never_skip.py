"""T035 (FR-013): slow engine, many chunks → all transcribed; lag rises then
falls; completed only after the backlog drains."""

from __future__ import annotations

from tests.conftest import wait_until
from tests.support.fake_capture import MIC_ID, SYSTEM_ID
from tests.support.fake_speech import seg


def test_backlog_drains_nothing_skipped(client, fake_provider, fake_engine):
    for i in range(6):
        fake_engine.script[("mic", i)] = [seg(6.0, 7.0, f"m{i}")]  # inside each chunk
    fake_engine.delay_s = 0.25  # 2 tracks × 6 chunks × 0.25 s ≈ 3 s of work for 60 s audio
    sid = client.post("/sessions", json={}).json()["id"]
    fake_provider.push_seconds(MIC_ID, 60.0)
    fake_provider.push_seconds(SYSTEM_ID, 60.0)

    lags = []

    def sample():
        t = client.get(f"/sessions/{sid}/transcript").json()
        lags.append(t["job"]["lag_s"] or 0.0)
        return len(t["segments"]) >= 6

    assert wait_until(sample, timeout_s=20)
    assert max(lags) > 0.0  # lag was visibly reported while behind

    client.post(f"/sessions/{sid}/stop")
    seen_finalising = False

    def done():
        nonlocal seen_finalising
        t = client.get(f"/sessions/{sid}/transcript").json()
        if t["state"] == "finalising":
            seen_finalising = True
        return t["state"] == "completed"

    assert wait_until(done, timeout_s=20)
    t = client.get(f"/sessions/{sid}/transcript").json()
    assert sorted(s["text"] for s in t["segments"]) == [f"m{i}" for i in range(6)]
    assert t["final"] is True and t["job"]["lag_s"] == 0.0
