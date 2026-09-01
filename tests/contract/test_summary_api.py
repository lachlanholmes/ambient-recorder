"""T013: summary endpoint contracts."""

from __future__ import annotations

from tests.conftest import wait_until
from tests.support.fake_capture import MIC_ID, SYSTEM_ID
from tests.support.fake_speech import seg

FINAL_NOTES = (
    "OVERVIEW: A short chat.\nKEY POINTS:\n- greeting exchanged [1]\n"
    "DECISIONS:\n- none\nACTION ITEMS:\n- none"
)
MAP_NOTES = "KEY POINTS:\n- greeting exchanged [1]\nDECISIONS:\n- none\nACTION ITEMS:\n- none"


def _finished_session(client, fake_provider, fake_engine) -> str:
    fake_engine.script[("mic", 0)] = [seg(1.0, 2.0, "hello there")]
    sid = client.post("/sessions", json={}).json()["id"]
    fake_provider.push_seconds(MIC_ID, 10.0)
    fake_provider.push_seconds(SYSTEM_ID, 10.0)
    assert wait_until(
        lambda: len(client.get(f"/sessions/{sid}/transcript").json()["segments"]) >= 1
    )
    client.post(f"/sessions/{sid}/stop")
    assert wait_until(
        lambda: client.get(f"/sessions/{sid}/transcript").json()["state"] == "completed"
    )
    return sid


def test_summarize_flow_and_statuses(client, fake_provider, fake_engine, fake_llm):
    fake_llm.script = [("NOTES:", MAP_NOTES), ("FINAL SUMMARY:", FINAL_NOTES)]
    sid = _finished_session(client, fake_provider, fake_engine)

    r = client.post(f"/sessions/{sid}/summarize")
    assert r.status_code == 202
    assert wait_until(lambda: client.get(f"/sessions/{sid}/summary").json()["state"] == "completed")
    s = client.get(f"/sessions/{sid}/summary").json()
    assert s["content"]["overview"].startswith("A short chat")
    assert s["content"]["key_points"][0]["citations"], "citations required"
    assert s["model"] == "fake-assistant test/none"

    listed = client.get(f"/sessions/{sid}/summaries").json()["summaries"]
    assert len(listed) == 1 and listed[0]["superseded"] is False
    by_id = client.get(f"/sessions/{sid}/summaries/{s['id']}")
    assert by_id.status_code == 200


def test_summarize_refusals(client, fake_provider, fake_engine):
    assert client.post("/sessions/nope/summarize").status_code == 404
    # active session → 409 transcript_not_final
    sid = client.post("/sessions", json={}).json()["id"]
    r = client.post(f"/sessions/{sid}/summarize")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "transcript_not_final"
    client.post(f"/sessions/{sid}/stop")
    # summary 404 before any request
    r2 = client.get(f"/sessions/{sid}/summary")
    assert r2.status_code == 404 and r2.json()["error"]["code"] == "summary_not_found"
