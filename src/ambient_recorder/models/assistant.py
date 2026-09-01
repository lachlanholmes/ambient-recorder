"""Assistant domain + API models — normative per specs/003 data-model.md
and contracts/rest-api.md."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from ambient_recorder.models.session import new_ulid, utcnow
from ambient_recorder.models.transcript import Speaker

V1_MAX_SCOPE = 1  # conversations scope exactly one session in v1


class SummaryState(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class TurnState(StrEnum):
    STREAMING = "streaming"
    COMPLETED = "completed"
    UNGROUNDED = "ungrounded"  # assertions with zero valid citations
    DECLINED = "declined"  # honest "not discussed in this meeting"
    FAILED = "failed"
    INTERRUPTED = "interrupted"  # restart mid-answer; streamed prefix kept


class TaskState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskKind(StrEnum):
    SUMMARY = "summary"
    ASK = "ask"


class AssistantReadinessState(StrEnum):
    READY = "ready"
    NOT_READY = "not_ready"  # runtime reachable, model missing / policy failed
    NOT_INSTALLED = "not_installed"  # runtime unreachable and never configured


# -- domain ---------------------------------------------------------------


class Citation(BaseModel):
    session_id: str
    transcript_id: str
    seq: int = Field(ge=0)
    start_s: float = Field(ge=0)


class SummaryItem(BaseModel):
    text: str
    citations: list[Citation] = Field(min_length=1)

    @field_validator("text")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("summary item text must be non-empty")
        return v


class ActionItem(BaseModel):
    text: str
    owner: Speaker
    deadline_text: str | None = None  # verbatim spoken deadline
    citations: list[Citation] = Field(min_length=1)


class SummaryContent(BaseModel):
    overview: str
    key_points: list[SummaryItem]
    decisions: list[SummaryItem]
    action_items: list[ActionItem]


class Summary(BaseModel):
    id: str = Field(default_factory=new_ulid)
    session_id: str
    transcript_id: str
    state: SummaryState = SummaryState.PENDING
    content: SummaryContent | None = None  # completed only
    model: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    completed_at: datetime | None = None
    failure_reason: str | None = None


class Conversation(BaseModel):
    """Top-level chat about a declared scope of sessions (v1: exactly one)."""

    id: str = Field(default_factory=new_ulid)
    session_ids: list[str] = Field(min_length=1, max_length=V1_MAX_SCOPE)
    created_at: datetime = Field(default_factory=utcnow)
    born_live: bool = False


class ConversationTurn(BaseModel):
    id: str = Field(default_factory=new_ulid)
    conversation_id: str
    seq: int = Field(default=0, ge=0)  # store-assigned
    question: str
    answer: str = ""
    citations: list[Citation] = Field(default_factory=list)
    watermark: str | None = None  # "final" or "live:<segment seq>"
    state: TurnState = TurnState.STREAMING
    asked_at: datetime = Field(default_factory=utcnow)
    completed_at: datetime | None = None

    @field_validator("question")
    @classmethod
    def _question_bounds(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("question must be non-empty")
        if len(v) > 2000:
            raise ValueError("question must be at most 2000 characters")
        return v


class AssistantTask(BaseModel):
    id: str = Field(default_factory=new_ulid)
    kind: TaskKind
    ref_id: str  # summary id or turn id
    session_id: str  # primary session (v1 scope[0] for asks)
    priority: int = 2  # 0 live ask, 1 ask, 2 summary
    state: TaskState = TaskState.QUEUED
    enqueued_at: datetime = Field(default_factory=utcnow)
    started_at: datetime | None = None
    ended_at: datetime | None = None
    failure_reason: str | None = None


# -- API ------------------------------------------------------------------


class AssistantReadiness(BaseModel):
    status: AssistantReadinessState
    ready: bool
    runtime: str | None = None
    model: str | None = None
    reason: str | None = None


class SummaryResponse(BaseModel):
    id: str
    session_id: str
    transcript_id: str
    state: SummaryState
    content: SummaryContent | None
    model: str | None
    created_at: datetime
    completed_at: datetime | None
    failure_reason: str | None
    task_state: TaskState | None = None  # while pending


class SummaryVersionInfo(BaseModel):
    id: str
    state: SummaryState
    superseded: bool
    model: str | None
    created_at: datetime


class SummaryListResponse(BaseModel):
    summaries: list[SummaryVersionInfo]


class ConversationCreateRequest(BaseModel):
    session_ids: list[str] = Field(min_length=1, max_length=V1_MAX_SCOPE)


class ConversationResponse(BaseModel):
    id: str
    session_ids: list[str]
    created_at: datetime
    born_live: bool


class TurnResponse(BaseModel):
    id: str
    conversation_id: str
    seq: int
    question: str
    answer: str
    citations: list[Citation]
    watermark: str | None
    state: TurnState
    asked_at: datetime
    completed_at: datetime | None


class ConversationDetail(ConversationResponse):
    turns: list[TurnResponse]


class ConversationListResponse(BaseModel):
    conversations: list[ConversationResponse]


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class AssistantTaskResponse(BaseModel):
    task_id: str
    kind: TaskKind
    ref_id: str
    state: TaskState


class TokenFrame(BaseModel):
    type: Literal["token"] = "token"
    turn_seq: int
    text: str


class TurnStatusFrame(BaseModel):
    type: Literal["status"] = "status"
    turn_seq: int
    state: TurnState
    citations: list[Citation] | None = None
    watermark: str | None = None
