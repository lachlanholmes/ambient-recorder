"""Assistant REST routes — contracts/rest-api.md (feature 003)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool

from ambient_recorder.errors import (
    AssistantNotReadyError,
    ConversationNotFoundError,
    SessionNotFoundError,
    SummaryNotFoundError,
    TranscriptNotFinalError,
)
from ambient_recorder.models.assistant import (
    AskRequest,
    AssistantReadiness,
    AssistantTaskResponse,
    Conversation,
    ConversationCreateRequest,
    ConversationDetail,
    ConversationListResponse,
    ConversationResponse,
    SummaryListResponse,
    SummaryResponse,
    TaskKind,
    TaskState,
    TurnResponse,
)
from ambient_recorder.models.transcript import TranscriptState

router = APIRouter()


def _astore(request: Request):
    return request.app.state.assistant_store


def _worker(request: Request):
    return request.app.state.assistant_worker


def _summary_response(store, s) -> SummaryResponse:
    task_state = None
    if s.state.value == "pending":
        for t in store.open_tasks():
            if t.ref_id == s.id:
                task_state = t.state
                break
        task_state = task_state or TaskState.QUEUED
    return SummaryResponse(
        id=s.id, session_id=s.session_id, transcript_id=s.transcript_id, state=s.state,
        content=s.content, model=s.model, created_at=s.created_at,
        completed_at=s.completed_at, failure_reason=s.failure_reason,
        task_state=task_state,
    )


@router.get("/assistant/readiness", response_model=AssistantReadiness)
async def readiness(request: Request) -> AssistantReadiness:
    return await run_in_threadpool(_worker(request).readiness)


@router.post("/sessions/{session_id}/summarize", response_model=AssistantTaskResponse,
             status_code=202)
async def summarize(request: Request, session_id: str):
    meta, tstore, worker = (request.app.state.metadata, request.app.state.transcripts,
                            _worker(request))
    session = await run_in_threadpool(meta.get_session, session_id)
    if session is None:
        raise SessionNotFoundError(session_id)
    transcript = await run_in_threadpool(tstore.current_transcript, session_id)
    if session.status == "active" or transcript is None or \
            transcript.state != TranscriptState.COMPLETED or not transcript.final:
        raise TranscriptNotFinalError(session_id)
    r = await run_in_threadpool(worker.readiness)
    if not r.ready:
        raise AssistantNotReadyError(r.reason or r.status.value)
    s = await run_in_threadpool(worker.request_summary, session_id, transcript.id)
    return AssistantTaskResponse(task_id=s.id, kind=TaskKind.SUMMARY, ref_id=s.id,
                                 state=TaskState.QUEUED)


@router.get("/sessions/{session_id}/summary", response_model=SummaryResponse)
async def current_summary(request: Request, session_id: str):
    store, meta = _astore(request), request.app.state.metadata
    if await run_in_threadpool(meta.get_session, session_id) is None:
        raise SessionNotFoundError(session_id)
    s = await run_in_threadpool(store.current_summary, session_id)
    if s is None:
        raise SummaryNotFoundError(session_id)
    return _summary_response(store, s)


@router.get("/sessions/{session_id}/summaries", response_model=SummaryListResponse)
async def list_summaries(request: Request, session_id: str):
    store, meta = _astore(request), request.app.state.metadata
    if await run_in_threadpool(meta.get_session, session_id) is None:
        raise SessionNotFoundError(session_id)
    return SummaryListResponse(
        summaries=await run_in_threadpool(store.list_summaries, session_id))


@router.get("/sessions/{session_id}/summaries/{summary_id}", response_model=SummaryResponse)
async def get_summary(request: Request, session_id: str, summary_id: str):
    store = _astore(request)
    s = await run_in_threadpool(store.get_summary, summary_id)
    if s is None or s.session_id != session_id:
        raise SummaryNotFoundError(summary_id)
    return _summary_response(store, s)


@router.post("/conversations", response_model=ConversationResponse, status_code=201)
async def create_conversation(request: Request, body: ConversationCreateRequest):
    store, meta, worker = _astore(request), request.app.state.metadata, _worker(request)
    for sid in body.session_ids:
        if await run_in_threadpool(meta.get_session, sid) is None:
            raise SessionNotFoundError(sid)
    r = await run_in_threadpool(worker.readiness)
    if not r.ready:
        raise AssistantNotReadyError(r.reason or r.status.value)
    active = request.app.state.engine.active_session_id
    c = Conversation(session_ids=body.session_ids,
                     born_live=active in body.session_ids)
    await run_in_threadpool(store.create_conversation, c)
    return ConversationResponse(id=c.id, session_ids=c.session_ids,
                                created_at=c.created_at, born_live=c.born_live)


@router.get("/conversations", response_model=ConversationListResponse)
async def list_conversations(request: Request, session_id: str | None = None):
    return ConversationListResponse(
        conversations=await run_in_threadpool(_astore(request).list_conversations, session_id))


@router.get("/conversations/{cid}", response_model=ConversationDetail)
async def get_conversation(request: Request, cid: str):
    c = await run_in_threadpool(_astore(request).get_conversation, cid)
    if c is None:
        raise ConversationNotFoundError(cid)
    return c


@router.post("/conversations/{cid}/ask", response_model=TurnResponse, status_code=202)
async def ask(request: Request, cid: str, body: AskRequest):
    store, worker = _astore(request), _worker(request)
    c = await run_in_threadpool(store.get_conversation, cid)
    if c is None:
        raise ConversationNotFoundError(cid)
    r = await run_in_threadpool(worker.readiness)
    if not r.ready:
        raise AssistantNotReadyError(r.reason or r.status.value)
    conv = Conversation(id=c.id, session_ids=c.session_ids, created_at=c.created_at,
                        born_live=c.born_live)
    turn = await run_in_threadpool(worker.request_ask, conv, body.question)
    return TurnResponse(
        id=turn.id, conversation_id=turn.conversation_id, seq=turn.seq,
        question=turn.question, answer="", citations=[], watermark=None,
        state=turn.state, asked_at=turn.asked_at, completed_at=None,
    )
