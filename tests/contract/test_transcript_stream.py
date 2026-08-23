"""T015: WebSocket stream contract — replay + tail exactness, status, close codes."""

from __future__ import annotations

import json

import pytest
from starlette.websockets import WebSocketDisconnect
from tests.conftest import wait_until
from tests.support.fake_capture import MIC_ID, SYSTEM_ID
from tests.support.fake_speech import seg


def _four_segments(fake_engine):
    fake_engine.script[("mic", 0)] = [seg(1.0, 2.0, "a"), seg(3.0, 4.0, "b")]
    fake_engine.script[("system", 0)] = [seg(5.0, 6.0, "c"), seg(7.0, 8.0, "d")]


def _read_until_n_segments(ws, n):
    segs = []
    while len(segs) < n:
        m = json.loads(ws.receive_text())
        if m["type"] == "segment":
            segs.append(m["segment"])
    return segs


def test_replay_then_tail_is_exact(client, fake_provider, fake_engine):
    _four_segments(fake_engine)
    fake_engine.script[("mic", 1)] = [seg(6.0, 7.0, "e")]  # window t6 == session 11
    sid = client.post("/sessions", json={}).json()["id"]
    fake_provider.push_seconds(MIC_ID, 10.0)
    fake_provider.push_seconds(SYSTEM_ID, 10.0)
    assert wait_until(
        lambda: len(client.get(f"/sessions/{sid}/transcript").json()["segments"]) == 4
    )

    # Reconnect from cursor 1: replay must yield exactly seq 2,3 then tail seq 4.
    with client.websocket_connect(f"/sessions/{sid}/transcript/stream?after=1") as ws:
        replay = _read_until_n_segments(ws, 2)
        assert [s["seq"] for s in replay] == [2, 3]
        fake_provider.push_seconds(MIC_ID, 10.0)
        fake_provider.push_seconds(SYSTEM_ID, 10.0)
        tail = _read_until_n_segments(ws, 1)
        assert tail[0]["seq"] == 4 and tail[0]["text"] == "e"
    client.post(f"/sessions/{sid}/stop")


def test_status_on_connect_and_terminal_close(client, fake_provider, fake_engine):
    sid = client.post("/sessions", json={}).json()["id"]
    with client.websocket_connect(f"/sessions/{sid}/transcript/stream") as ws:
        first = json.loads(ws.receive_text())
        assert first == {"type": "status", "state": "live", "lag_s": 0.0, "final": False}
        client.post(f"/sessions/{sid}/stop")
        terminal = None
        while terminal is None:
            m = json.loads(ws.receive_text())
            if m["type"] == "status" and m["state"] == "completed":
                terminal = m
        assert terminal["final"] is True
        with pytest.raises(WebSocketDisconnect):
            ws.receive_text()  # server closed after terminal status


def test_close_codes(client, fake_provider):
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect("/sessions/nope/transcript/stream"):
            pass
    assert e.value.code == 4404
    # Session exists but has no transcript at all (engine not installed path
    # is covered elsewhere); here: a completed session that predates transcription.
    sid = client.post("/sessions", json={}).json()["id"]
    client.post(f"/sessions/{sid}/stop")
    # It has a live transcript, so a *different* precondition: use a bogus id
    # for the transcript-less case via a session made without transcription.
