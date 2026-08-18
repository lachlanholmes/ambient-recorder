"""Guard against accidental API surface growth (T033)."""

from __future__ import annotations

EXPECTED = {
    ("/health", "get"),
    ("/devices", "get"),
    ("/sessions", "post"),
    ("/sessions", "get"),
    ("/sessions/{session_id}", "get"),
    ("/sessions/{session_id}/stop", "post"),
}


def test_openapi_contains_exactly_the_documented_routes(app):
    spec = app.openapi()
    actual = {
        (path, method)
        for path, methods in spec["paths"].items()
        for method in methods
    }
    assert actual == EXPECTED
