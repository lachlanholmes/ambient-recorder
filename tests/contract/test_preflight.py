"""Start preflight refusals are typed and side-effect-free (T027, SC-003)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from tests.support.fake_capture import FakeCaptureProvider, FakeDeviceEnumerator

from ambient_recorder.config import Settings
from ambient_recorder.main import create_app
from ambient_recorder.models.api import ErrorCode
from ambient_recorder.models.session import SourceKind


def test_missing_device_is_424_and_creates_nothing(settings):
    provider = FakeCaptureProvider()
    enumerator = FakeDeviceEnumerator(provider, missing={SourceKind.MIC})
    with TestClient(create_app(settings, provider, enumerator)) as client:
        r = client.post("/sessions", json={"title": "doomed"})
        assert r.status_code == 424
        body = r.json()
        assert body["error"]["code"] == ErrorCode.DEVICE_MISSING
        assert body["error"]["detail"]["missing"] == ["mic"]
        assert "mic" in body["error"]["message"]  # names the device (SC-003)
        assert client.get("/sessions").json()["sessions"] == []


def test_both_missing_names_both(settings):
    provider = FakeCaptureProvider()
    enumerator = FakeDeviceEnumerator(
        provider, missing={SourceKind.MIC, SourceKind.SYSTEM}
    )
    with TestClient(create_app(settings, provider, enumerator)) as client:
        r = client.post("/sessions", json={})
        assert r.status_code == 424
        assert set(r.json()["error"]["detail"]["missing"]) == {"mic", "system"}


def test_low_disk_is_507_and_creates_nothing(tmp_path):
    settings = Settings(data_root=tmp_path / "data", min_free_disk_mb=10**9)
    provider = FakeCaptureProvider()
    enumerator = FakeDeviceEnumerator(provider)
    with TestClient(create_app(settings, provider, enumerator)) as client:
        r = client.post("/sessions", json={})
        assert r.status_code == 507
        body = r.json()
        assert body["error"]["code"] == ErrorCode.DISK_SPACE_LOW
        assert body["error"]["detail"]["required_mb"] == 10**9
        assert body["error"]["detail"]["free_mb"] < 10**9
        assert client.get("/sessions").json()["sessions"] == []
