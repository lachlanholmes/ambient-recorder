"""App assembly: startup validation, reconciliation, route/handler wiring.

`create_app` takes injected providers so the entire API runs device- and
model-free in tests; `python -m ambient_recorder` wires the real WASAPI
provider and the real speech-engine factory.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ambient_recorder.api.errors import register_error_handlers
from ambient_recorder.api.routes import router
from ambient_recorder.api.transcription_routes import router as transcription_router
from ambient_recorder.api.ws import router as ws_router
from ambient_recorder.audio.engine import CaptureEngine
from ambient_recorder.audio.protocols import CaptureProvider, DeviceEnumerator
from ambient_recorder.config import Settings
from ambient_recorder.logging import jlog, setup_logging
from ambient_recorder.storage.chunks import FsChunkStore
from ambient_recorder.storage.metadata import SqliteMetadataStore, reconcile_interrupted
from ambient_recorder.storage.transcripts import SqliteTranscriptStore, reconcile_transcription
from ambient_recorder.transcription.protocols import EngineFactory
from ambient_recorder.transcription.stream import SegmentStream
from ambient_recorder.transcription.worker import TranscriptionWorker


def create_app(
    settings: Settings,
    provider: CaptureProvider,
    enumerator: DeviceEnumerator,
    engine_factory: EngineFactory | None = None,
) -> FastAPI:
    setup_logging()
    # FR-010 second line of defence: Settings already rejects non-loopback
    # hosts at validation time; assert the invariant here for belt+braces.
    assert settings.host in ("127.0.0.1", "localhost", "::1")

    chunk_store = FsChunkStore(settings.sessions_root)
    metadata = SqliteMetadataStore(settings.db_path)
    engine = CaptureEngine(provider, enumerator, chunk_store, metadata, settings)

    if engine_factory is None:
        from ambient_recorder.transcription.readiness import DefaultEngineFactory

        engine_factory = DefaultEngineFactory(settings)
    transcripts = SqliteTranscriptStore(settings.db_path)
    stream = SegmentStream()
    worker = TranscriptionWorker(engine_factory, transcripts, chunk_store, stream, settings)
    engine.add_session_observer(worker.on_session_event)
    engine.add_chunk_observer(worker.on_chunk)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        jlog("startup", pid=os.getpid(), config=settings.model_dump(mode="json"))
        reconciled = reconcile_interrupted(metadata, chunk_store)
        jlog("reconciliation_done", sessions_reconciled=reconciled)
        reconcile_transcription(transcripts, engine.active_session_id)
        jlog(
            "device_readiness", sources=[r.model_dump(mode="json") for r in enumerator.readiness()]
        )
        jlog("transcription_readiness", **engine_factory.readiness().model_dump(mode="json"))
        worker.start()
        worker.requeue_open_on_demand()
        yield
        worker.shutdown()
        transcripts.close()
        metadata.close()

    app = FastAPI(title="ambient-recorder", lifespan=lifespan)
    app.state.engine = engine
    app.state.metadata = metadata
    app.state.enumerator = enumerator
    app.state.transcripts = transcripts
    app.state.transcription_worker = worker
    app.state.segment_stream = stream
    app.include_router(router)
    app.include_router(transcription_router)
    app.include_router(ws_router)
    register_error_handlers(app)
    return app
