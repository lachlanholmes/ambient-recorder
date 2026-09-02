"""Static UI serving — specs/004 contracts/ui-consumption.md (R2).

Mounted at `/` AFTER every router, so all API and WS routes keep
winning (Starlette resolves routes in registration order; the mount is
the catch-all). Every UI response carries the local-only CSP as a
response header — it covers cached pages too, unlike a meta tag — and
the index is `no-cache` so UI updates apply on reload. A missing ui/
directory (dev edge) degrades: warning + 404 at `/`, API unaffected.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from ambient_recorder.logging import jlog

UI_DIR = Path(__file__).resolve().parent.parent / "ui"

CSP = "default-src 'self'; connect-src 'self' ws://127.0.0.1:* ws://localhost:*"


class _UIFiles(StaticFiles):
    """StaticFiles with the CSP on every response, no-cache on the index."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        response.headers["Content-Security-Policy"] = CSP
        if path in (".", "index.html"):
            response.headers["Cache-Control"] = "no-cache"
        return response


def mount_ui(app: FastAPI) -> None:
    if not (UI_DIR / "index.html").is_file():
        jlog("ui_dir_missing", level=logging.WARNING, ui_dir=str(UI_DIR))
        return
    app.mount("/", _UIFiles(directory=UI_DIR, html=True), name="ui")
