"""T020: live pipeline end-to-end with fake capture + fake engine."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient
from tests.conftest import wait_until
from tests.support.fake_capture import MIC_ID, SYSTEM_ID
from tests.support.fake_speech import seg

from ambient_recorder.main import create_app


def _script(fake_engine):
    # Chunk 0 windows (no tail yet): mic says hello, system says a longer line.
    fake_engine.script[("mic", 0)] = [seg(1.0, 2.5, "hello everyone")]
    fake_engine.script[("system", 0)] = [seg(2.0, 6.0, "welcome to the weekly sync")]
    # Chunk 1 windows start 5 s before chunk 1 (tail), i.e. window t=0 == session 5.0.
    fake_engine.script[("mic", 1)] = [seg(7.0, 9.0, "sounds good")]  # session 12–14
    fake_engine.script[("system", 1)] = [seg(6.0, 8.5, "let's begin")]  # session 11–13.5


def test_live_end_to_end(app, client, fake_provider, fake_engine, settings, engine_factory):
    _script(fake_engine)
    sid = client.post("/sessions", json={"title": "live"}).json()["id"]

    # Live transcript exists immediately (auto-start, FR-010).
    t = client.get(f"/sessions/{sid}/transcript").json()
    assert t["mode"] == "live" and t["state"] == "live" and t["job"]["state"] == "running"

    with client.websocket_connect(f"/sessions/{sid}/transcript/stream") as ws:
        first = json.loads(ws.receive_text())
        assert first["type"] == "status" and first["state"] == "live"

        fake_provider.push_seconds(MIC_ID, 20.0)  # two full chunks per track
        fake_provider.push_seconds(SYSTEM_ID, 20.0)

        got = []
        while len(got) < 4:
            msg = json.loads(ws.receive_text())
            if msg["type"] == "segment":
                got.append(msg["segment"])
        texts = {(g["source"], g["text"]) for g in got}
        assert texts == {
            ("me", "hello everyone"),
            ("them", "welcome to the weekly sync"),
            ("me", "sounds good"),
            ("them", "let's begin"),
        }
        # Session-relative timing preserved through the rolling window.
        by_text = {g["text"]: g for g in got}
        assert by_text["sounds good"]["start_s"] == 12.0
        assert by_text["let's begin"]["end_s"] == 13.5

        client.post(f"/sessions/{sid}/stop")
        final = None
        while final is None:
            msg = json.loads(ws.receive_text())
            if msg["type"] == "status" and msg["state"] == "completed":
                final = msg
        assert final["final"] is True

    # REST view identical to the streamed set, ordered chronologically.
    rest = client.get(f"/sessions/{sid}/transcript").json()
    assert rest["state"] == "completed" and rest["final"] is True
    assert [s["text"] for s in rest["segments"]] == [
        "hello everyone",
        "welcome to the weekly sync",
        "let's begin",
        "sounds good",
    ]
    assert [s["seq"] for s in sorted(rest["segments"], key=lambda s: s["seq"])] == [0, 1, 2, 3]

    # Survives a restart (FR-004): fresh app on the same data root.
    with TestClient(
        create_app(settings, fake_provider, app.state.enumerator, engine_factory)
    ) as c2:
        again = c2.get(f"/sessions/{sid}/transcript").json()
        assert again["id"] == rest["id"] and len(again["segments"]) == 4


def test_after_cursor_on_rest(app, client, fake_provider, fake_engine):
    _script(fake_engine)
    sid = client.post("/sessions", json={}).json()["id"]
    fake_provider.push_seconds(MIC_ID, 20.0)
    fake_provider.push_seconds(SYSTEM_ID, 20.0)
    assert wait_until(
        lambda: len(client.get(f"/sessions/{sid}/transcript").json()["segments"]) == 4
    )
    partial = client.get(f"/sessions/{sid}/transcript?after=1").json()
    assert sorted(s["seq"] for s in partial["segments"]) == [2, 3]
    client.post(f"/sessions/{sid}/stop")
