"""T027: assistant failure never touches capture or transcription."""

from __future__ import annotations

from tests.conftest import wait_until
from tests.support.fake_capture import MIC_ID, SYSTEM_ID
from tests.support.fake_speech import seg


def test_engine_failure_mid_ask_leaves_recording_untouched(
    client, fake_provider, fake_engine, fake_llm
):
    fake_engine.script[("mic", 0)] = [seg(1.0, 2.0, "live words")]
    sid = client.post("/sessions", json={}).json()["id"]
    fake_provider.push_seconds(MIC_ID, 10.0)
    fake_provider.push_seconds(SYSTEM_ID, 10.0)
    assert wait_until(
        lambda: len(client.get(f"/sessions/{sid}/transcript").json()["segments"]) >= 1
    )

    fake_llm.fail_after_calls = 0
    cid = client.post("/conversations", json={"session_ids": [sid]}).json()["id"]
    client.post(f"/conversations/{cid}/ask", json={"question": "anything?"})
    assert wait_until(
        lambda: client.get(f"/conversations/{cid}").json()["turns"][0]["state"] == "failed"
    )

    # capture and live transcription continue
    fake_engine.script[("mic", 1)] = [seg(6.0, 7.0, "still transcribing")]
    fake_provider.push_seconds(MIC_ID, 10.0)
    fake_provider.push_seconds(SYSTEM_ID, 10.0)
    assert wait_until(lambda: client.get(f"/sessions/{sid}").json()["chunk_counts"]["mic"] >= 2)
    assert wait_until(
        lambda: len(client.get(f"/sessions/{sid}/transcript").json()["segments"]) >= 2
    )
    stopped = client.post(f"/sessions/{sid}/stop").json()
    assert stopped["status"] == "completed"
