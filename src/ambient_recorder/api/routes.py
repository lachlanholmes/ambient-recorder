"""HTTP surface — exactly the six routes in contracts/rest-api.md."""

from __future__ import annotations

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool

import ambient_recorder
from ambient_recorder.errors import SessionNotFoundError
from ambient_recorder.models.api import (
    DeviceReadinessResponse,
    HealthResponse,
    ReadinessStatus,
    SessionCreateRequest,
    SessionDetail,
    SessionListResponse,
)

router = APIRouter()


def _engine(request: Request):
    return request.app.state.engine


def _metadata(request: Request):
    return request.app.state.metadata


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    return HealthResponse(
        version=ambient_recorder.__version__,
        active_session_id=_engine(request).active_session_id,
    )


@router.get("/devices", response_model=DeviceReadinessResponse)
async def devices(request: Request) -> DeviceReadinessResponse:
    enumerator = request.app.state.enumerator
    previous = await run_in_threadpool(_metadata(request).last_device_ids)
    sources = enumerator.readiness(previous or None)
    ready = all(s.status != ReadinessStatus.MISSING for s in sources)
    return DeviceReadinessResponse(sources=sources, ready=ready)


@router.post("/sessions", response_model=SessionDetail, status_code=201)
async def create_session(request: Request, body: SessionCreateRequest) -> SessionDetail:
    return await run_in_threadpool(_engine(request).start_session, body.title)


@router.post("/sessions/{session_id}/stop", response_model=SessionDetail)
async def stop_session(request: Request, session_id: str) -> SessionDetail:
    return await run_in_threadpool(_engine(request).stop_session, session_id)


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(request: Request) -> SessionListResponse:
    sessions = await run_in_threadpool(_metadata(request).list_sessions)
    return SessionListResponse(sessions=sessions)


@router.get("/sessions/{session_id}", response_model=SessionDetail)
async def get_session(request: Request, session_id: str) -> SessionDetail:
    detail = await run_in_threadpool(_metadata(request).get_session, session_id)
    if detail is None:
        raise SessionNotFoundError(session_id)
    return detail
