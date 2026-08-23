"""`python -m ambient_recorder` — run the recorder with real WASAPI devices."""

from __future__ import annotations

import socket
import sys

import uvicorn

from ambient_recorder.config import Settings, load_settings


def claim_port(settings: Settings) -> socket.socket:
    """Bind the API port BEFORE any startup work touches the database.

    The bound socket is the single-instance lock: a second recorder pointed
    at the same port exits here, before its startup reconciliation could
    finalise the running instance's active session as interrupted
    (split-brain found 2026-08-20). Exits with a clear message on conflict.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((settings.host, settings.port))
    except OSError:
        sock.close()
        sys.exit(
            f"Another recorder is already listening on {settings.host}:{settings.port} "
            f"— check http://{settings.host}:{settings.port}/health, or set AMBREC_PORT "
            "to run a second instance against a different AMBREC_DATA_ROOT."
        )
    sock.listen(128)
    return sock


def run() -> None:
    settings = load_settings()
    sock = claim_port(settings)
    try:
        from ambient_recorder.audio.wasapi import (
            WasapiCaptureProvider,
            WasapiDeviceEnumerator,
        )
    except ImportError as e:
        sys.exit(
            "The WASAPI capture provider is not implemented yet "
            f"(constitution gate (d) pending, T019): {e}"
        )
    from ambient_recorder.main import create_app

    provider = WasapiCaptureProvider()
    app = create_app(settings, provider, WasapiDeviceEnumerator(provider))
    config = uvicorn.Config(app, log_level="warning")
    uvicorn.Server(config).run(sockets=[sock])


if __name__ == "__main__":
    run()
