"""`python -m ambient_recorder` — run the recorder with real WASAPI devices."""

from __future__ import annotations

import sys

import uvicorn

from ambient_recorder.config import load_settings
from ambient_recorder.main import create_app


def run() -> None:
    settings = load_settings()
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
    provider = WasapiCaptureProvider()
    app = create_app(settings, provider, WasapiDeviceEnumerator(provider))
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="warning")


if __name__ == "__main__":
    run()
