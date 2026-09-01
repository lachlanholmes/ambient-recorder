"""Contract: static UI serving — specs/004 contracts/ui-consumption.md.

`/` serves the shell with the local-only CSP; every API route keeps
winning over the mount; a missing ui/ directory degrades to 404 + a
warning with the API unaffected; the OpenAPI surface stays exactly the
001-003 route set (mounts are not schema paths).
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from tests.contract.test_openapi_surface import EXPECTED

from ambient_recorder.main import create_app

CSP = "default-src 'self'; connect-src 'self' ws://127.0.0.1:* ws://localhost:*"


def test_root_serves_index_with_csp_and_no_cache(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert r.headers["content-security-policy"] == CSP
    assert r.headers["cache-control"] == "no-cache"
    assert "<html" in r.text.lower()


def test_assets_served_with_csp(client):
    r = client.get("/style.css")
    assert r.status_code == 200
    assert r.headers["content-security-policy"] == CSP
    r = client.get("/js/app.js")
    assert r.status_code == 200
    assert r.headers["content-security-policy"] == CSP


def test_api_routes_still_win_over_the_mount(client):
    r = client.get("/sessions")
    assert r.status_code == 200
    assert "sessions" in r.json()
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_unknown_path_is_404(client):
    assert client.get("/no-such-asset.js").status_code == 404


def test_missing_ui_dir_degrades_with_warning(
    settings, fake_provider, enumerator, engine_factory, assistant_factory, tmp_path, monkeypatch
):
    import ambient_recorder.api.static_ui as static_ui

    events: list[str] = []
    monkeypatch.setattr(static_ui, "UI_DIR", tmp_path / "no-ui-here")
    monkeypatch.setattr(static_ui, "jlog", lambda event, **kw: events.append(event))
    app = create_app(settings, fake_provider, enumerator, engine_factory, assistant_factory)
    with TestClient(app) as c:
        assert c.get("/").status_code == 404
        assert c.get("/health").status_code == 200
    assert "ui_dir_missing" in events


def test_openapi_surface_unchanged_by_ui_mount(app):
    spec = app.openapi()
    actual = {(path, method) for path, methods in spec["paths"].items() for method in methods}
    assert actual == EXPECTED
