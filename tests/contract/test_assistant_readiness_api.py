"""T026: assistant readiness contract (three-way + 503 parity)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from tests.support.fake_assistant import FakeAssistantFactory

from ambient_recorder.main import create_app
from ambient_recorder.models.assistant import AssistantReadinessState


def test_ready(client):
    r = client.get("/assistant/readiness").json()
    assert r["status"] == "ready" and r["ready"] and r["runtime"] == "fake-assistant"


def _app_with(settings, fake_provider, enumerator, engine_factory, status, reason):
    return create_app(
        settings,
        fake_provider,
        enumerator,
        engine_factory,
        FakeAssistantFactory(status=status, reason=reason),
    )


def test_not_ready_and_503_share_reason(settings, fake_provider, enumerator, engine_factory):
    app = _app_with(
        settings,
        fake_provider,
        enumerator,
        engine_factory,
        AssistantReadinessState.NOT_READY,
        "model_missing: run `ollama pull x`",
    )
    with TestClient(app) as client:
        r = client.get("/assistant/readiness").json()
        assert r["status"] == "not_ready" and "ollama pull" in r["reason"]
        sid = client.post("/sessions", json={}).json()["id"]
        client.post(f"/sessions/{sid}/stop")
        resp = client.post("/conversations", json={"session_ids": [sid]})
        assert resp.status_code == 503
        assert "ollama pull" in resp.json()["error"]["detail"]["reason"]


def test_not_installed_layering(settings, fake_provider, enumerator, engine_factory):
    app = _app_with(
        settings,
        fake_provider,
        enumerator,
        engine_factory,
        AssistantReadinessState.NOT_INSTALLED,
        "install Ollama",
    )
    with TestClient(app) as client:
        assert client.get("/assistant/readiness").json()["status"] == "not_installed"
        # capture + transcription untouched (FR-009)
        sid = client.post("/sessions", json={}).json()["id"]
        assert client.post(f"/sessions/{sid}/stop").json()["status"] == "completed"
        assert client.post(f"/sessions/{sid}/summarize").status_code in (409, 503)
