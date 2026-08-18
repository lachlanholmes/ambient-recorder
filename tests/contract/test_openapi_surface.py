"""Guard against accidental API surface growth (001 T033, 002 T037)."""

from __future__ import annotations

EXPECTED = {
    # feature 001
    ("/health", "get"),
    ("/devices", "get"),
    ("/sessions", "post"),
    ("/sessions", "get"),
    ("/sessions/{session_id}", "get"),
    ("/sessions/{session_id}/stop", "post"),
    # feature 002 (contracts/rest-api.md)
    ("/transcription/readiness", "get"),
    ("/sessions/{session_id}/transcript", "get"),
    ("/sessions/{session_id}/transcripts", "get"),
    ("/sessions/{session_id}/transcripts/{transcript_id}", "get"),
    ("/sessions/{session_id}/transcribe", "post"),
}
EXPECTED_WS = {"/sessions/{session_id}/transcript/stream"}


def test_openapi_contains_exactly_the_documented_routes(app):
    spec = app.openapi()
    actual = {
        (path, method)
        for path, methods in spec["paths"].items()
        for method in methods
    }
    assert actual == EXPECTED


def test_websocket_routes_exactly_documented(app):
    from starlette.routing import WebSocketRoute

    ws = {r.path for r in app.routes if isinstance(r, WebSocketRoute)}
    assert ws == EXPECTED_WS
