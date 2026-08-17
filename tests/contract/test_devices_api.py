"""GET /devices readiness contract (T026)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from tests.support.fake_capture import FakeCaptureProvider, FakeDeviceEnumerator

from ambient_recorder.main import create_app
from ambient_recorder.models.api import DeviceReadinessResponse
from ambient_recorder.models.session import SourceKind


def test_all_present(client):
    r = client.get("/devices")
    assert r.status_code == 200
    body = DeviceReadinessResponse.model_validate(r.json())
    assert body.ready is True
    assert {s.kind: s.status for s in body.sources} == {
        SourceKind.MIC: "present", SourceKind.SYSTEM: "present"
    }


def test_missing_mic_reported_and_not_ready(settings):
    provider = FakeCaptureProvider()
    enumerator = FakeDeviceEnumerator(provider, missing={SourceKind.MIC})
    with TestClient(create_app(settings, provider, enumerator)) as client:
        body = DeviceReadinessResponse.model_validate(client.get("/devices").json())
        assert body.ready is False
        statuses = {s.kind: s.status for s in body.sources}
        assert statuses[SourceKind.MIC] == "missing"
        assert statuses[SourceKind.SYSTEM] == "present"


def test_default_changed_flagged_but_ready(client, enumerator, fake_provider):
    sid = client.post("/sessions", json={}).json()["id"]
    client.post(f"/sessions/{sid}/stop")
    enumerator.ids[SourceKind.SYSTEM] = "fake-new-speakers"
    body = DeviceReadinessResponse.model_validate(client.get("/devices").json())
    statuses = {s.kind: s.status for s in body.sources}
    assert statuses[SourceKind.SYSTEM] == "default_changed"
    assert statuses[SourceKind.MIC] == "present"
    assert body.ready is True  # default_changed does not block start (v1)
