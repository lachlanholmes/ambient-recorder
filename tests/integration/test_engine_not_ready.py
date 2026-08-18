"""T027: not-ready → visible failed; not-installed → skipped (state none)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from tests.support.fake_speech import FakeEngineFactory

from ambient_recorder.main import create_app
from ambient_recorder.models.transcript import ReadinessState


def test_installed_but_not_ready_fails_visibly(settings, fake_provider, enumerator):
    factory = FakeEngineFactory(status=ReadinessState.NOT_READY, reason="model_missing: run x")
    with TestClient(create_app(settings, fake_provider, enumerator, factory)) as client:
        assert client.get("/transcription/readiness").json()["status"] == "not_ready"
        sid = client.post("/sessions", json={}).json()["id"]
        t = client.get(f"/sessions/{sid}/transcript").json()
        assert t["state"] == "failed"
        assert t["job"]["failure_reason"].startswith("engine_not_ready")
        assert client.post(f"/sessions/{sid}/stop").json()["status"] == "completed"
        # On-demand refused with 503 while not ready.
        r = client.post(f"/sessions/{sid}/transcribe")
        assert r.status_code == 503
        assert r.json()["error"]["code"] == "transcription_not_ready"


def test_not_installed_skips_live_mode(settings, fake_provider, enumerator):
    factory = FakeEngineFactory(status=ReadinessState.NOT_INSTALLED, reason="pip install")
    with TestClient(create_app(settings, fake_provider, enumerator, factory)) as client:
        assert client.get("/transcription/readiness").json()["status"] == "not_installed"
        sid = client.post("/sessions", json={}).json()["id"]
        r = client.get(f"/sessions/{sid}/transcript")
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "transcript_not_found"  # state "none"
        assert client.get(f"/sessions/{sid}/transcripts").json()["transcripts"] == []
        assert client.post(f"/sessions/{sid}/stop").json()["status"] == "completed"
