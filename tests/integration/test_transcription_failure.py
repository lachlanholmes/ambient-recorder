"""T026: engine failure mid-live → failed with reason; recording continues."""

from __future__ import annotations

from tests.conftest import wait_until
from tests.support.fake_capture import MIC_ID, SYSTEM_ID
from tests.support.fake_speech import seg


def test_engine_failure_does_not_touch_recording(client, fake_provider, fake_engine):
    fake_engine.script[("mic", 0)] = [seg(1.0, 2.0, "before the crash")]
    fake_engine.fail_after_calls = 2  # third transcribe() raises
    sid = client.post("/sessions", json={}).json()["id"]
    fake_provider.push_seconds(MIC_ID, 20.0)
    fake_provider.push_seconds(SYSTEM_ID, 20.0)
    assert wait_until(lambda: client.get(f"/sessions/{sid}/transcript").json()["state"] == "failed")

    t = client.get(f"/sessions/{sid}/transcript").json()
    assert "engine_error" in t["job"]["failure_reason"]
    assert [s["text"] for s in t["segments"]] == ["before the crash"]  # kept

    # Capture is unaffected: chunks keep landing and stop succeeds.
    fake_provider.push_seconds(MIC_ID, 10.0)
    assert wait_until(lambda: client.get(f"/sessions/{sid}").json()["chunk_counts"]["mic"] >= 3)
    stopped = client.post(f"/sessions/{sid}/stop").json()
    assert stopped["status"] == "completed"
    assert stopped["chunk_counts"]["mic"] == 3
