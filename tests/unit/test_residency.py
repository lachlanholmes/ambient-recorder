"""T025: keep-alive residency — engine released after idle, kept during
sessions. Uses the worker's internals with a real (fast) idle thread
replaced by direct calls."""

from __future__ import annotations

import time

from tests.conftest import wait_until
from tests.support.fake_capture import MIC_ID, SYSTEM_ID


def test_engine_released_after_idle(
    app, client, fake_provider, fake_llm, assistant_factory, monkeypatch
):
    worker = app.state.assistant_worker
    monkeypatch.setattr(worker.settings, "assistant_idle_unload_s", 0)

    # trigger a load via an ask on a finished session
    sid = client.post("/sessions", json={}).json()["id"]
    fake_provider.push_seconds(MIC_ID, 10.0)
    fake_provider.push_seconds(SYSTEM_ID, 10.0)
    client.post(f"/sessions/{sid}/stop")
    assert wait_until(
        lambda: client.get(f"/sessions/{sid}/transcript").json()["state"] == "completed"
    )
    cid = client.post("/conversations", json={"session_ids": [sid]}).json()["id"]
    client.post(f"/conversations/{cid}/ask", json={"question": "hello?"})
    assert wait_until(lambda: assistant_factory.load_calls >= 1)

    # no active session + zero idle threshold → the watch loop releases
    worker._last_activity = time.monotonic() - 1
    assert wait_until(lambda: assistant_factory.release_calls >= 1, timeout_s=40)


def test_engine_kept_while_session_active(
    app, client, fake_provider, fake_llm, assistant_factory, monkeypatch
):
    worker = app.state.assistant_worker
    monkeypatch.setattr(worker.settings, "assistant_idle_unload_s", 0)
    sid = client.post("/sessions", json={}).json()["id"]  # active session
    fake_provider.push_seconds(MIC_ID, 10.0)
    fake_provider.push_seconds(SYSTEM_ID, 10.0)
    assert wait_until(
        lambda: len(client.get(f"/sessions/{sid}/transcript").json()["segments"]) >= 0
    )
    cid = client.post("/conversations", json={"session_ids": [sid]}).json()["id"]
    client.post(f"/conversations/{cid}/ask", json={"question": "hi?"})
    assert wait_until(lambda: assistant_factory.load_calls >= 1)
    worker._last_activity = time.monotonic() - 100
    time.sleep(0.5)  # give the idle thread a chance to (wrongly) fire
    assert assistant_factory.release_calls == 0  # session active → never released
    client.post(f"/sessions/{sid}/stop")
