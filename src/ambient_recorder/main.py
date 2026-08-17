"""App assembly: startup validation, reconciliation, route/handler wiring.

`create_app` takes injected providers so the entire API runs device-free
in tests; `python -m ambient_recorder` wires the real WASAPI provider.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ambient_recorder.api.errors import register_error_handlers
from ambient_recorder.api.routes import router
from ambient_recorder.audio.engine import CaptureEngine
from ambient_recorder.audio.protocols import CaptureProvider, DeviceEnumerator
from ambient_recorder.config import Settings
from ambient_recorder.logging import jlog, setup_logging
from ambient_recorder.storage.chunks import FsChunkStore
from ambient_recorder.storage.metadata import SqliteMetadataStore, reconcile_interrupted


def create_app(
    settings: Settings,
    provider: CaptureProvider,
    enumerator: DeviceEnumerator,
) -> FastAPI:
    setup_logging()
    # FR-010 second line of defence: Settings already rejects non-loopback
    # hosts at validation time; assert the invariant here for belt+braces.
    assert settings.host in ("127.0.0.1", "localhost", "::1")

    chunk_store = FsChunkStore(settings.sessions_root)
    metadata = SqliteMetadataStore(settings.db_path)
    engine = CaptureEngine(provider, enumerator, chunk_store, metadata, settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        jlog("startup", pid=os.getpid(),
             config=settings.model_dump(mode="json"))
        reconciled = reconcile_interrupted(metadata, chunk_store)
        jlog("reconciliation_done", sessions_reconciled=reconciled)
        jlog("device_readiness",
             sources=[r.model_dump(mode="json") for r in enumerator.readiness()])
        yield
        metadata.close()

    app = FastAPI(title="ambient-recorder", lifespan=lifespan)
    app.state.engine = engine
    app.state.metadata = metadata
    app.state.enumerator = enumerator
    app.include_router(router)
    register_error_handlers(app)
    return app
