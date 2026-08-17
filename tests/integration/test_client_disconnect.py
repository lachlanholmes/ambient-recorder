"""FR-009: the session belongs to the engine, not the client (T024)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from tests.conftest import wait_until
from tests.support.fake_capture import MIC_ID


def test_capture_survives_client_disconnect(app, client, fake_provider):
    # `client` holds the app lifespan open; simulate a UI client that
    # starts a session and then goes away entirely.
    ui_client = TestClient(app)
    sid = ui_client.post("/sessions", json={"title": "meeting"}).json()["id"]
    del ui_client  # UI gone

    fake_provider.push_seconds(MIC_ID, 11.0)  # capture continues regardless

    assert app.state.engine.active_session_id == sid
    # A brand-new client can inspect and stop the same session; the writer
    # thread persists asynchronously, so poll for the first chunk.
    late_client = TestClient(app)
    assert wait_until(
        lambda: late_client.get(f"/sessions/{sid}").json()["chunk_counts"]["mic"] >= 1
    ), "audio was not persisted while the client was disconnected"
    detail = late_client.get(f"/sessions/{sid}").json()
    assert detail["status"] == "active"
    assert late_client.post(f"/sessions/{sid}/stop").json()["status"] == "completed"
