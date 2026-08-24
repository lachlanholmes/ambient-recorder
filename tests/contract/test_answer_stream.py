"""T019: WS answer-stream contract — prefix replay, tail, terminal close."""

from __future__ import annotations

import json

import pytest
from starlette.websockets import WebSocketDisconnect
from tests.conftest import wait_until
from tests.support.fake_capture import MIC_ID, SYSTEM_ID
from tests.support.fake_speech import seg


def _finished_session(client, fake_provider, fake_engine) -> str:
    fake_engine.script[("mic", 0)] = [seg(1.0, 2.0, "the date is thursday")]
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


def test_stream_tokens_then_terminal_status(client, fake_provider, fake_engine, fake_llm):
    fake_llm.script = [("QUESTION:", "The date is Thursday [1].")]
    fake_llm.delay_s = 0.05  # slow enough to catch the stream live
    sid = _finished_session(client, fake_provider, fake_engine)
    cid = client.post("/conversations", json={"session_ids": [sid]}).json()["id"]
    client.post(f"/conversations/{cid}/ask", json={"question": "what is the date?"})

    with client.websocket_connect(f"/conversations/{cid}/stream") as ws:
        text, terminal = "", None
        while terminal is None:
            m = json.loads(ws.receive_text())
            if m["type"] == "token":
                text += m["text"]
            elif m["type"] == "status" and m["state"] != "streaming":
                terminal = m
        assert "Thursday" in text
        assert terminal["state"] == "completed"
        assert terminal["citations"] and terminal["citations"][0]["session_id"] == sid
        assert terminal["watermark"] == "final"
        with pytest.raises(WebSocketDisconnect):
            ws.receive_text()  # closed after terminal

    turn = client.get(f"/conversations/{cid}").json()["turns"][0]
    assert turn["state"] == "completed" and "Thursday" in turn["answer"]


def test_no_inflight_turn_sends_latest_terminal_and_closes(
    client, fake_provider, fake_engine, fake_llm
):
    fake_llm.script = [("QUESTION:", "The date is Thursday [1].")]
    sid = _finished_session(client, fake_provider, fake_engine)
    cid = client.post("/conversations", json={"session_ids": [sid]}).json()["id"]
    client.post(f"/conversations/{cid}/ask", json={"question": "date?"})
    assert wait_until(
        lambda: client.get(f"/conversations/{cid}").json()["turns"][0]["state"] == "completed"
    )
    with client.websocket_connect(f"/conversations/{cid}/stream") as ws:
        m = json.loads(ws.receive_text())
        assert m["type"] == "status" and m["state"] == "completed"
        with pytest.raises(WebSocketDisconnect):
            ws.receive_text()


def test_unknown_conversation_4404(client):
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect("/conversations/nope/stream"):
            pass
    assert e.value.code == 4404
