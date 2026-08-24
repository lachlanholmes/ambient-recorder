"""Assistant worker (research R5/R6, T015/T020/T023/T025).

One thread, priority queue: live ask (0) > ask (1) > summary (2). One
engine request in flight at a time. Reads transcripts via the transcript
store; publishes answer tokens to the shared SegmentStream-style pub/sub.
Never touches capture or STT internals (constitution VII).
"""

from __future__ import annotations

import heapq
import itertools
import threading
import time
from dataclasses import dataclass, field

from ambient_recorder.assistant.grounding import GroundingVerdict, validate_citations
from ambient_recorder.assistant.prompts import QA_SYSTEM, qa_prompt
from ambient_recorder.assistant.protocols import (
    AssistantEngine,
    AssistantEngineFactory,
    EngineError,
    EngineNotReadyError,
)
from ambient_recorder.assistant.retrieval import select_excerpts
from ambient_recorder.assistant.summarize import MalformedOutputError, summarize
from ambient_recorder.config import Settings
from ambient_recorder.logging import jlog
from ambient_recorder.models.assistant import (
    AssistantTask,
    Conversation,
    ConversationTurn,
    Summary,
    TaskKind,
    TaskState,
    TokenFrame,
    TurnState,
    TurnStatusFrame,
)
from ambient_recorder.models.session import utcnow
from ambient_recorder.storage.assistant import SqliteAssistantStore
from ambient_recorder.storage.transcripts import SqliteTranscriptStore
from ambient_recorder.transcription.stream import SegmentStream

PRIORITY_LIVE_ASK = 0
PRIORITY_ASK = 1
PRIORITY_SUMMARY = 2


@dataclass(order=True)
class _Item:
    priority: int
    order: int
    task_id: str = field(compare=False, default="")
    kind: str = field(compare=False, default="")  # "summary" | "ask" | "shutdown"


class AssistantWorker:
    def __init__(
        self,
        factory: AssistantEngineFactory,
        store: SqliteAssistantStore,
        transcripts: SqliteTranscriptStore,
        stream: SegmentStream,
        settings: Settings,
        active_session_id_fn=lambda: None,
    ):
        self.factory = factory
        self.store = store
        self.transcripts = transcripts
        self.stream = stream
        self.settings = settings
        self.active_session_id_fn = active_session_id_fn
        self._engine: AssistantEngine | None = None
        self._engine_lock = threading.Lock()
        self._q: list[_Item] = []
        self._qcv = threading.Condition()
        self._counter = itertools.count()
        self._last_activity = time.monotonic()
        self._session_active = False
        self._thread = threading.Thread(target=self._run, name="assistant", daemon=True)
        self._idle_thread = threading.Thread(target=self._idle_watch, name="assistant-idle",
                                             daemon=True)

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        self._thread.start()
        self._idle_thread.start()

    def shutdown(self, timeout: float = 5.0) -> None:
        self._push(_Item(-1, next(self._counter), kind="shutdown"))
        self._thread.join(timeout=timeout)

    def readiness(self):
        return self.factory.readiness()

    # -- session residency (T025): called from the capture engine observer --

    def on_session_event(self, session_id: str, event: str) -> None:
        if event == "started":
            self._session_active = True
            self._last_activity = time.monotonic()
        elif event in ("stopped", "finalized"):
            self._session_active = False
            self._last_activity = time.monotonic()

    def _idle_watch(self) -> None:
        while True:
            time.sleep(30)
            if self._session_active or self._engine is None:
                continue
            idle = time.monotonic() - self._last_activity
            if idle >= self.settings.assistant_idle_unload_s:
                with self._engine_lock:
                    if self._engine is not None:
                        self._engine = None
                        self.factory.release()
                        jlog("assistant_engine_released", idle_s=round(idle))

    # -- public API used by routes ----------------------------------------

    def request_summary(self, session_id: str, transcript_id: str) -> Summary:
        s = Summary(session_id=session_id, transcript_id=transcript_id)
        task = AssistantTask(kind=TaskKind.SUMMARY, ref_id=s.id, session_id=session_id,
                             priority=PRIORITY_SUMMARY)
        self.store.create_summary(s, task)
        self._push(_Item(task.priority, next(self._counter), task.id, "summary"))
        return s

    def request_ask(self, conversation: Conversation, question: str) -> ConversationTurn:
        session_id = conversation.session_ids[0]  # v1 scope
        live = self.active_session_id_fn() == session_id
        turn = ConversationTurn(conversation_id=conversation.id, question=question)
        task = AssistantTask(
            kind=TaskKind.ASK, ref_id=turn.id, session_id=session_id,
            priority=PRIORITY_LIVE_ASK if live else PRIORITY_ASK,
        )
        turn = self.store.create_turn(turn, task)
        self._push(_Item(task.priority, next(self._counter), task.id, "ask"))
        return turn

    def requeue_open(self) -> None:
        task = self.store.next_queued()
        seen: set[str] = set()
        while task is not None and task.id not in seen:
            seen.add(task.id)
            self._push(_Item(task.priority, next(self._counter), task.id, task.kind.value))
            task = None  # next_queued re-consulted as tasks complete

    # -- internals ---------------------------------------------------------

    def _push(self, item: _Item) -> None:
        with self._qcv:
            heapq.heappush(self._q, item)
            self._qcv.notify()

    def _get_engine(self) -> AssistantEngine:
        with self._engine_lock:
            if self._engine is None:
                self._engine = self.factory.load()
                jlog("assistant_engine_loaded", descriptor=self._engine.descriptor)
            return self._engine

    def _run(self) -> None:
        while True:
            with self._qcv:
                while not self._q:
                    self._qcv.wait()
                item = heapq.heappop(self._q)
            if item.kind == "shutdown":
                return
            self._last_activity = time.monotonic()
            try:
                if item.kind == "summary":
                    self._run_summary(item.task_id)
                else:
                    self._run_ask(item.task_id)
            except Exception as e:  # noqa: BLE001 — worker must not die
                jlog("assistant_worker_error", task_id=item.task_id, error=repr(e))
            self._last_activity = time.monotonic()

    # -- summaries ---------------------------------------------------------

    def _generate_text(self, prompt: str, system: str) -> str:
        engine = self._get_engine()
        return "".join(c.text for c in engine.generate(prompt, system=system, max_tokens=1024))

    def _run_summary(self, task_id: str) -> None:
        task = self._start_task(task_id)
        if task is None:
            return
        summary = self.store.get_summary(task.ref_id)
        segments = self.transcripts.segments_after(summary.transcript_id, -1)
        t0 = time.perf_counter()
        try:
            content = summarize(
                segments, summary.session_id, self._generate_text,
                window_s=self.settings.summary_window_s,
                budget_tokens=self.settings.excerpt_budget_tokens,
            )
        except (EngineError, EngineNotReadyError, MalformedOutputError) as e:
            self.store.fail_summary(summary.id, f"{type(e).__name__}: {e}")
            self.store.update_task(task_id, state=TaskState.FAILED, ended_at=utcnow(),
                                   failure_reason=str(e))
            jlog("assistant_task_failed", task_id=task_id, kind="summary", reason=str(e))
            return
        model = self._engine.descriptor if self._engine else "unknown"
        self.store.complete_summary(summary.id, content, model)
        self.store.update_task(task_id, state=TaskState.COMPLETED, ended_at=utcnow())
        jlog("assistant_task_completed", task_id=task_id, kind="summary",
             wall_s=round(time.perf_counter() - t0, 1),
             action_items=len(content.action_items))

    # -- asks --------------------------------------------------------------

    def _run_ask(self, task_id: str) -> None:
        task = self._start_task(task_id)
        if task is None:
            return
        turn = self.store.get_turn(task.ref_id)
        conv = self.store.get_conversation(turn.conversation_id)
        session_id = conv.session_ids[0]

        transcript = self.transcripts.current_transcript(session_id)
        if transcript is None:
            transcript = self.transcripts.pending_transcript(session_id)
        if transcript is None:
            self._fail_turn(task_id, turn.id, "no transcript exists for the scoped session")
            return
        segments = self.transcripts.segments_after(transcript.id, -1)
        live = self.active_session_id_fn() == session_id
        watermark = f"live:{max((s.seq for s in segments), default=-1)}" if live else "final"

        history_texts = [t.question for t in conv.turns if t.id != turn.id]
        history_pairs = [(t.question, t.answer) for t in conv.turns
                         if t.id != turn.id and t.state == TurnState.COMPLETED]
        excerpts = select_excerpts(
            turn.question, history_texts, segments, session_id=session_id,
            budget_tokens=self.settings.excerpt_budget_tokens, live=live,
        )
        prompt = qa_prompt(excerpts, history_pairs, turn.question)
        if live:
            job = self.transcripts.get_job(transcript.id)
            lag = (job.lag_s or 0.0) if job else 0.0
            if lag > 5.0:
                prompt += (
                    f"\n(Note: transcription is ~{int(lag)}s behind; the very "
                    "latest moments may be missing — say so if relevant.)"
                )

        t0 = time.perf_counter()
        raw_parts: list[str] = []
        first_token_s: float | None = None
        try:
            engine = self._get_engine()
            for chunk in engine.generate(prompt, system=QA_SYSTEM, max_tokens=768):
                if chunk.text:
                    if first_token_s is None:
                        first_token_s = time.perf_counter() - t0
                    raw_parts.append(chunk.text)
                    self.store.append_answer_text(turn.id, chunk.text)
                    self.stream.publish(conv.id, TokenFrame(turn_seq=turn.seq, text=chunk.text))
        except (EngineError, EngineNotReadyError) as e:
            self._fail_turn(task_id, turn.id, f"engine_error: {e}", conv_id=conv.id,
                            turn_seq=turn.seq)
            return

        raw = "".join(raw_parts)
        cleaned, citations, verdict = validate_citations(raw, excerpts)
        state = {
            GroundingVerdict.GROUNDED: TurnState.COMPLETED,
            GroundingVerdict.DECLINED: TurnState.DECLINED,
            GroundingVerdict.UNGROUNDED: TurnState.UNGROUNDED,
        }[verdict]
        self.store.set_turn_answer(turn.id, cleaned)
        self.store.finish_turn(turn.id, state, citations, watermark)
        self.store.update_task(task_id, state=TaskState.COMPLETED, ended_at=utcnow())
        self.stream.publish(conv.id, TurnStatusFrame(
            turn_seq=turn.seq, state=state, citations=citations, watermark=watermark))
        self.stream.close(conv.id)
        jlog("assistant_task_completed", task_id=task_id, kind="ask", state=state.value,
             first_token_s=round(first_token_s or 0.0, 2),
             wall_s=round(time.perf_counter() - t0, 1), citations=len(citations))

    # -- shared ------------------------------------------------------------

    def _start_task(self, task_id: str):
        tasks = {t.id: t for t in self.store.open_tasks()}
        task = tasks.get(task_id)
        if task is None or task.state != TaskState.QUEUED:
            return None
        self.store.update_task(task_id, state=TaskState.RUNNING, started_at=utcnow())
        jlog("assistant_task_started", task_id=task_id, kind=task.kind.value,
             priority=task.priority)
        return task

    def _fail_turn(self, task_id: str, turn_id: str, reason: str,
                   conv_id: str | None = None, turn_seq: int | None = None) -> None:
        self.store.finish_turn(turn_id, TurnState.FAILED, [], None)
        self.store.update_task(task_id, state=TaskState.FAILED, ended_at=utcnow(),
                               failure_reason=reason)
        if conv_id is not None and turn_seq is not None:
            self.stream.publish(conv_id, TurnStatusFrame(turn_seq=turn_seq,
                                                         state=TurnState.FAILED))
            self.stream.close(conv_id)
        jlog("assistant_task_failed", task_id=task_id, kind="ask", reason=reason)
