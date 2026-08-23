"""Transcription REST routes — contracts/rest-api.md (feature 002)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool

from ambient_recorder.errors import (
    SessionNotFoundError,
    SessionStillActiveError,
    TranscriptionAlreadyRunningError,
    TranscriptionNotReadyError,
    TranscriptNotFoundError,
)
from ambient_recorder.models.transcript import (
    JobInfo,
    PendingJobInfo,
    Transcript,
    TranscriptionJobResponse,
    TranscriptionReadiness,
    TranscriptListResponse,
    TranscriptResponse,
)

router = APIRouter()


def _store(request: Request):
    return request.app.state.transcripts


def _worker(request: Request):
    return request.app.state.transcription_worker


def _metadata(request: Request):
    return request.app.state.metadata


def _response(store, t: Transcript, after: int = -1) -> TranscriptResponse:
    job = store.get_job(t.id)
    pending = store.pending_transcript(t.session_id)
    pj = None
    if pending is not None and pending.id != t.id:
        pjob = store.get_job(pending.id)
        if pjob is not None:
            pj = PendingJobInfo(
                transcript_id=pending.id,
                state=pjob.state,
                progress_chunks=pjob.progress_chunks,
                total_chunks=pjob.total_chunks,
            )
    segs = store.segments_after(t.id, after)
    segs.sort(key=lambda s: (s.start_s, s.seq))
    return TranscriptResponse(
        id=t.id,
        session_id=t.session_id,
        mode=t.mode,
        state=t.state,
        final=t.final,
        model=t.model,
        segments=segs,
        job=JobInfo(
            state=job.state,
            lag_s=job.lag_s,
            progress_chunks=job.progress_chunks,
            total_chunks=job.total_chunks,
            failure_reason=job.failure_reason,
        )
        if job
        else JobInfo(state="failed"),  # type: ignore[arg-type]
        pending_job=pj,
    )


@router.get("/transcription/readiness", response_model=TranscriptionReadiness)
async def readiness(request: Request) -> TranscriptionReadiness:
    return await run_in_threadpool(_worker(request).readiness)


@router.get("/sessions/{session_id}/transcript", response_model=TranscriptResponse)
async def current_transcript(request: Request, session_id: str, after: int = -1):
    store, meta = _store(request), _metadata(request)
    if await run_in_threadpool(meta.get_session, session_id) is None:
        raise SessionNotFoundError(session_id)
    t = await run_in_threadpool(store.current_transcript, session_id)
    if t is None:
        # A pending/failed-only session still surfaces its state (SC-005).
        t = await run_in_threadpool(store.pending_transcript, session_id)
        if t is None:
            latest = await run_in_threadpool(store.list_transcripts, session_id)
            if not latest:
                raise TranscriptNotFoundError(session_id)
            t = await run_in_threadpool(store.get_transcript, latest[0].id)
    return await run_in_threadpool(_response, store, t, after)


@router.get("/sessions/{session_id}/transcripts", response_model=TranscriptListResponse)
async def list_transcripts(request: Request, session_id: str):
    store, meta = _store(request), _metadata(request)
    if await run_in_threadpool(meta.get_session, session_id) is None:
        raise SessionNotFoundError(session_id)
    return TranscriptListResponse(
        transcripts=await run_in_threadpool(store.list_transcripts, session_id)
    )


@router.get("/sessions/{session_id}/transcripts/{transcript_id}", response_model=TranscriptResponse)
async def get_transcript(request: Request, session_id: str, transcript_id: str, after: int = -1):
    store = _store(request)
    t = await run_in_threadpool(store.get_transcript, transcript_id)
    if t is None or t.session_id != session_id:
        raise TranscriptNotFoundError(transcript_id)
    return await run_in_threadpool(_response, store, t, after)


@router.post(
    "/sessions/{session_id}/transcribe", response_model=TranscriptionJobResponse, status_code=202
)
async def transcribe(request: Request, session_id: str):
    store, meta, worker = _store(request), _metadata(request), _worker(request)
    session = await run_in_threadpool(meta.get_session, session_id)
    if session is None:
        raise SessionNotFoundError(session_id)
    if session.status == "active":
        raise SessionStillActiveError(session_id)
    if await run_in_threadpool(store.running_on_demand, session_id) is not None:
        raise TranscriptionAlreadyRunningError(session_id)
    r = await run_in_threadpool(worker.readiness)
    if not r.ready:
        raise TranscriptionNotReadyError(r.reason or r.status.value)
    t = await run_in_threadpool(worker.request_on_demand, session_id)
    return TranscriptionJobResponse(transcript_id=t.id, session_id=session_id, state="queued")  # type: ignore[arg-type]
