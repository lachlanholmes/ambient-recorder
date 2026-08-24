"""FakeAssistantEngine / FakeAssistantFactory (T007) — scripted, model-free.

Scripting: `engine.script` is a list of (matcher, response) pairs; the
first matcher found in the prompt (substring) wins. Response text is
yielded in small chunks with optional delay. Unmatched prompts yield
`default_response`.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator

from ambient_recorder.models.assistant import AssistantReadiness, AssistantReadinessState
from ambient_recorder.assistant.protocols import (
    EngineError,
    EngineNotReadyError,
    GenerationChunk,
)


class FakeAssistantEngine:
    descriptor = "fake-assistant test/none"

    def __init__(self) -> None:
        self.script: list[tuple[str, str]] = []  # (prompt substring, response)
        self.default_response = "not discussed in this meeting"
        self.delay_s = 0.0  # per chunk
        self.chunk_chars = 12
        self.fail_after_calls: int | None = None
        self.calls: list[str] = []  # prompts, in order
        self._lock = threading.Lock()

    def generate(
        self, prompt: str, *, system: str | None = None, max_tokens: int = 1024
    ) -> Iterator[GenerationChunk]:
        with self._lock:
            self.calls.append(prompt)
            if self.fail_after_calls is not None and len(self.calls) > self.fail_after_calls:
                raise EngineError("scripted engine failure")
        text = self.default_response
        for matcher, response in self.script:
            if matcher in prompt:
                text = response
                break
        for i in range(0, len(text), self.chunk_chars):
            if self.delay_s:
                time.sleep(self.delay_s)
            yield GenerationChunk(text=text[i : i + self.chunk_chars])
        yield GenerationChunk(text="", done=True)


class FakeAssistantFactory:
    def __init__(
        self,
        engine: FakeAssistantEngine | None = None,
        status: AssistantReadinessState = AssistantReadinessState.READY,
        reason: str | None = None,
    ):
        self.engine = engine or FakeAssistantEngine()
        self.status = status
        self.reason = reason
        self.load_calls = 0
        self.release_calls = 0

    def readiness(self) -> AssistantReadiness:
        ready = self.status == AssistantReadinessState.READY
        return AssistantReadiness(
            status=self.status,
            ready=ready,
            runtime="fake-assistant" if ready else None,
            model="test" if ready else None,
            reason=self.reason if not ready else None,
        )

    def load(self):
        self.load_calls += 1
        if self.status != AssistantReadinessState.READY:
            raise EngineNotReadyError(self.readiness())
        return self.engine

    def release(self) -> None:
        self.release_calls += 1
