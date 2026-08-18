from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ambient_recorder.config import Settings
from ambient_recorder.main import create_app
from tests.support.fake_capture import FakeCaptureProvider, FakeDeviceEnumerator


@pytest.fixture
def fake_provider() -> FakeCaptureProvider:
    return FakeCaptureProvider()


@pytest.fixture
def enumerator(fake_provider) -> FakeDeviceEnumerator:
    return FakeDeviceEnumerator(fake_provider)


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(data_root=tmp_path / "data", min_free_disk_mb=0)


@pytest.fixture
def app(settings, fake_provider, enumerator):
    return create_app(settings, fake_provider, enumerator)


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


def wait_until(condition, timeout_s: float = 5.0, interval_s: float = 0.02) -> bool:
    """Poll until `condition()` is truthy; writer threads persist asynchronously."""
    import time

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(interval_s)
    return bool(condition())
