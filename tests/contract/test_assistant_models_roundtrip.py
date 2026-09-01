"""SC-006: every 003 contract model round-trips (T006)."""

from __future__ import annotations

import pytest

from ambient_recorder.models.assistant import (
    ActionItem,
    AskRequest,
    AssistantReadiness,
    AssistantReadinessState,
    AssistantTask,
    AssistantTaskResponse,
    Citation,
    Conversation,
    ConversationCreateRequest,
    ConversationDetail,
    ConversationListResponse,
    ConversationResponse,
    ConversationTurn,
    Summary,
    SummaryContent,
    SummaryItem,
    SummaryListResponse,
    SummaryResponse,
    SummaryState,
    SummaryVersionInfo,
    TaskKind,
    TaskState,
    TokenFrame,
    TurnResponse,
    TurnState,
    TurnStatusFrame,
)
from ambient_recorder.models.session import utcnow
from ambient_recorder.models.transcript import Speaker

_CIT = Citation(session_id="s", transcript_id="t", seq=41, start_s=724.1)
_ITEM = SummaryItem(text="dashboard feedback positive", citations=[_CIT])
_ACTION = ActionItem(
    text="draft pricing options", owner=Speaker.ME, deadline_text="by Friday", citations=[_CIT]
)
_CONTENT = SummaryContent(
    overview="A review.", key_points=[_ITEM], decisions=[_ITEM], action_items=[_ACTION]
)
_TURN = TurnResponse(
    id="t1",
    conversation_id="c1",
    seq=0,
    question="what date?",
    answer="Thursday [3]",
    citations=[_CIT],
    watermark="live:213",
    state=TurnState.COMPLETED,
    asked_at=utcnow(),
    completed_at=utcnow(),
)

SAMPLES = [
    _CIT,
    _ITEM,
    _ACTION,
    _CONTENT,
    Summary(
        session_id="s",
        transcript_id="t",
        state=SummaryState.COMPLETED,
        content=_CONTENT,
        model="fake",
    ),
    Conversation(session_ids=["s"], born_live=True),
    ConversationTurn(conversation_id="c1", question="who said that?"),
    AssistantTask(kind=TaskKind.ASK, ref_id="t1", session_id="s", priority=0),
    AssistantReadiness(
        status=AssistantReadinessState.NOT_READY,
        ready=False,
        runtime="ollama 0.5",
        reason="model_missing: run x",
    ),
    SummaryResponse(
        id="x",
        session_id="s",
        transcript_id="t",
        state=SummaryState.PENDING,
        content=None,
        model=None,
        created_at=utcnow(),
        completed_at=None,
        failure_reason=None,
        task_state=TaskState.RUNNING,
    ),
    SummaryVersionInfo(
        id="x", state=SummaryState.COMPLETED, superseded=True, model="m", created_at=utcnow()
    ),
    SummaryListResponse(summaries=[]),
    ConversationCreateRequest(session_ids=["s"]),
    ConversationResponse(id="c1", session_ids=["s"], created_at=utcnow(), born_live=False),
    ConversationDetail(
        id="c1", session_ids=["s"], created_at=utcnow(), born_live=False, turns=[_TURN]
    ),
    ConversationListResponse(conversations=[]),
    AskRequest(question="what did they say about pricing?"),
    AssistantTaskResponse(task_id="a", kind=TaskKind.SUMMARY, ref_id="x", state=TaskState.QUEUED),
    TokenFrame(turn_seq=4, text="The new date "),
    TurnStatusFrame(turn_seq=4, state=TurnState.INTERRUPTED),
]


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda s: type(s).__name__)
def test_roundtrip_identity(sample):
    dumped = sample.model_dump(mode="json")
    assert type(sample).model_validate(dumped).model_dump(mode="json") == dumped


def test_scope_validation():
    with pytest.raises(ValueError):
        ConversationCreateRequest(session_ids=[])
    with pytest.raises(ValueError):
        ConversationCreateRequest(session_ids=["a", "b"])  # v1: exactly one


def test_question_validation():
    with pytest.raises(ValueError):
        ConversationTurn(conversation_id="c", question="  ")
    with pytest.raises(ValueError):
        AskRequest(question="x" * 2001)
