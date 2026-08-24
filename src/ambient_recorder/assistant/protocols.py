"""Assistant Protocols — normative per specs/003 contracts/protocols.md.

Implementations: assistant/ollama_engine.py (real, gate c),
tests/support/fake_assistant.py (scripted token streams).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from ambient_recorder.models.assistant import (
    AssistantReadiness,
    AssistantTask,
    Citation,
    Conversation,
    ConversationDetail,
    ConversationResponse,
    ConversationTurn,
    Summary,
    SummaryContent,
    SummaryVersionInfo,
    TurnState,
)


class GenerationChunk(BaseModel):
    text: str
    done: bool = False


class EngineError(Exception):
    pass


class EngineNotReadyError(Exception):
    def __init__(self, readiness: AssistantReadiness):
        self.readiness = readiness
        super().__init__(readiness.reason or readiness.status.value)


@runtime_checkable
class AssistantEngine(Protocol):
    @property
    def descriptor(self) -> str: ...

    def generate(
        self, prompt: str, *, system: str | None = None, max_tokens: int = 1024
    ) -> Iterator[GenerationChunk]: ...


@runtime_checkable
class AssistantEngineFactory(Protocol):
    def readiness(self) -> AssistantReadiness: ...

    def load(self) -> AssistantEngine: ...

    def release(self) -> None: ...


@runtime_checkable
class AssistantStore(Protocol):
    def create_summary(self, s: Summary, task: AssistantTask) -> None: ...

    def complete_summary(self, summary_id: str, content: SummaryContent, model: str) -> None: ...

    def fail_summary(self, summary_id: str, reason: str) -> None: ...

    def create_conversation(self, c: Conversation) -> None: ...

    def create_turn(self, t: ConversationTurn, task: AssistantTask) -> ConversationTurn: ...

    def append_answer_text(self, turn_id: str, text: str) -> None: ...

    def finish_turn(
        self,
        turn_id: str,
        state: TurnState,
        citations: list[Citation],
        watermark: str | None,
    ) -> None: ...

    def update_task(self, task_id: str, **fields) -> None: ...

    def current_summary(self, session_id: str) -> Summary | None: ...

    def list_summaries(self, session_id: str) -> list[SummaryVersionInfo]: ...

    def get_summary(self, summary_id: str) -> Summary | None: ...

    def get_conversation(self, cid: str) -> ConversationDetail | None: ...

    def get_turn(self, turn_id: str) -> ConversationTurn | None: ...

    def list_conversations(
        self, session_id: str | None = None
    ) -> list[ConversationResponse]: ...

    def open_tasks(self) -> list[AssistantTask]: ...

    def next_queued(self) -> AssistantTask | None: ...
