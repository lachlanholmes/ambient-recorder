"""T023: live in-meeting asks — transcript-so-far grounding, watermark,
lag caveat, continue post-meeting."""

from __future__ import annotations

from tests.conftest import wait_until
from tests.support.fake_capture import MIC_ID, SYSTEM_ID
from tests.support.fake_speech import seg


def test_live_ask_grounded_on_transcript_so_far(client, fake_provider, fake_engine, fake_llm):
    fake_engine.script[("mic", 0)] = [seg(1.0, 2.0, "the deadline is march third")]
    sid = client.post("/sessions", json={}).json()["id"]
    fake_provider.push_seconds(MIC_ID, 10.0)
    fake_provider.push_seconds(SYSTEM_ID, 10.0)
    assert wait_until(
        lambda: len(client.get(f"/sessions/{sid}/transcript").json()["segments"]) >= 1
    )

    cid = client.post("/conversations", json={"session_ids": [sid]}).json()["id"]
    fake_llm.script = [("deadline", "March third [1].")]
    client.post(f"/conversations/{cid}/ask", json={"question": "what is the deadline?"})
    assert wait_until(
        lambda: client.get(f"/conversations/{cid}").json()["turns"][0]["state"] == "completed"
    )
    turn = client.get(f"/conversations/{cid}").json()["turns"][0]
    assert turn["watermark"].startswith("live:")
    assert turn["citations"][0]["session_id"] == sid

    # conversation continues after stop, against the final transcript
    client.post(f"/sessions/{sid}/stop")
    assert wait_until(
        lambda: client.get(f"/sessions/{sid}/transcript").json()["state"] == "completed"
    )
    fake_llm.script = [("deadline", "Still March third [1].")]
    client.post(f"/conversations/{cid}/ask", json={"question": "confirm the deadline?"})
    assert wait_until(
        lambda: client.get(f"/conversations/{cid}").json()["turns"][1]["state"] == "completed"
    )
    assert client.get(f"/conversations/{cid}").json()["turns"][1]["watermark"] == "final"


def test_live_ask_priority_over_summary(client, fake_provider, fake_engine, fake_llm):
    """T024: a live ask jumps a queued summary (priority 0 < 2)."""
    fake_engine.script[("mic", 0)] = [seg(1.0, 2.0, "old meeting content")]
    old = client.post("/sessions", json={}).json()["id"]
    fake_provider.push_seconds(MIC_ID, 10.0)
    fake_provider.push_seconds(SYSTEM_ID, 10.0)
    assert wait_until(
        lambda: len(client.get(f"/sessions/{old}/transcript").json()["segments"]) >= 1
    )
    client.post(f"/sessions/{old}/stop")
    assert wait_until(
        lambda: client.get(f"/sessions/{old}/transcript").json()["state"] == "completed"
    )

    fake_llm.delay_s = 0.2
    fake_llm.script = [
        ("NOTES:", "KEY POINTS:\n- old content [1]\nDECISIONS:\n- none\nACTION ITEMS:\n- none"),
        (
            "FINAL SUMMARY:",
            "OVERVIEW: Old.\nKEY POINTS:\n- old content [1]\n"
            "DECISIONS:\n- none\nACTION ITEMS:\n- none",
        ),
        ("just said", "You said hello [1]."),
    ]
    # occupy the worker with a summary, then queue another summary + a live ask
    client.post(f"/sessions/{old}/summarize")
    client.post(f"/sessions/{old}/summarize")

    live_sid = client.post("/sessions", json={}).json()["id"]
    fake_engine.script[("mic", 1)] = [seg(1.0, 2.0, "hello from the live meeting")]
    fake_provider.push_seconds(MIC_ID, 10.0)
    fake_provider.push_seconds(SYSTEM_ID, 10.0)
    assert wait_until(
        lambda: len(client.get(f"/sessions/{live_sid}/transcript").json()["segments"]) >= 1
    )
    cid = client.post("/conversations", json={"session_ids": [live_sid]}).json()["id"]
    client.post(f"/conversations/{cid}/ask", json={"question": "what did I say just said?"})

    # the live ask must complete while at least one summary is still pending
    assert wait_until(
        lambda: client.get(f"/conversations/{cid}").json()["turns"][0]["state"]
        in ("completed", "declined", "ungrounded")
    )
    versions = client.get(f"/sessions/{old}/summaries").json()["summaries"]
    assert any(v["state"] == "pending" for v in versions), (
        "live ask should have jumped ahead of the queued summary"
    )
    client.post(f"/sessions/{live_sid}/stop")
    fake_llm.delay_s = 0.0
