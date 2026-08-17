"""Error envelope + /health + FR-010 loopback-bind guard (T013)."""

from __future__ import annotations

import pytest

from ambient_recorder.config import Settings
from ambient_recorder.models.api import ErrorCode, ErrorResponse


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["active_session_id"] is None


def test_unknown_session_yields_typed_envelope(client):
    r = client.get("/sessions/does-not-exist")
    assert r.status_code == 404
    parsed = ErrorResponse.model_validate(r.json())
    assert parsed.error.code == ErrorCode.SESSION_NOT_FOUND
    assert parsed.error.detail["session_id"] == "does-not-exist"


def test_validation_error_uses_envelope(client):
    r = client.post("/sessions", json={"title": "x" * 300})
    assert r.status_code == 422
    parsed = ErrorResponse.model_validate(r.json())
    assert parsed.error.code == ErrorCode.VALIDATION_ERROR


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.10", "example.com"])
def test_config_rejects_non_loopback_host(host):
    with pytest.raises(ValueError, match="loopback"):
        Settings(host=host)


def test_config_accepts_loopback():
    assert Settings(host="127.0.0.1").host == "127.0.0.1"
