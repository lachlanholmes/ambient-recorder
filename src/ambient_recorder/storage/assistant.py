"""SQLite AssistantStore (research R7) + assistant startup reconciliation.

Shares the existing database. The assistant worker is the only writer.
Conversations are top-level with a session scope join table (analyze
decision 2026-08-24).
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from ambient_recorder.logging import jlog
from ambient_recorder.models.assistant import (
    AssistantTask,
    Citation,
    Conversation,
    ConversationDetail,
    ConversationResponse,
    ConversationTurn,
    Summary,
    SummaryContent,
    SummaryState,
    SummaryVersionInfo,
    TaskKind,
    TaskState,
    TurnResponse,
    TurnState,
)
from ambient_recorder.models.session import utcnow

_SCHEMA = """
CREATE TABLE IF NOT EXISTS summaries (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    transcript_id TEXT NOT NULL,
    state TEXT NOT NULL,
    content TEXT,
    model TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    failure_reason TEXT
);
CREATE INDEX IF NOT EXISTS summaries_by_session ON summaries(session_id, created_at DESC);
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    born_live INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS conversation_sessions (
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    session_id TEXT NOT NULL,
    PRIMARY KEY (conversation_id, session_id)
);
CREATE INDEX IF NOT EXISTS conv_sessions_by_session ON conversation_sessions(session_id);
CREATE TABLE IF NOT EXISTS conversation_turns (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    seq INTEGER NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL DEFAULT '',
    citations TEXT NOT NULL DEFAULT '[]',
    watermark TEXT,
    state TEXT NOT NULL,
    asked_at TEXT NOT NULL,
    completed_at TEXT,
    UNIQUE (conversation_id, seq)
);
CREATE TABLE IF NOT EXISTS assistant_tasks (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    ref_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    priority INTEGER NOT NULL,
    state TEXT NOT NULL,
    enqueued_at TEXT NOT NULL,
    started_at TEXT,
    ended_at TEXT,
    failure_reason TEXT
);
"""


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


class SqliteAssistantStore:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(str(db_path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock, self._db:
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.executescript(_SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # -- writes ------------------------------------------------------------

    def create_summary(self, s: Summary, task: AssistantTask) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO summaries VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    s.id,
                    s.session_id,
                    s.transcript_id,
                    s.state.value,
                    s.content.model_dump_json() if s.content else None,
                    s.model,
                    _iso(s.created_at),
                    _iso(s.completed_at),
                    s.failure_reason,
                ),
            )
            self._insert_task(task)

    def complete_summary(self, summary_id: str, content: SummaryContent, model: str) -> None:
        with self._lock, self._db:
            self._db.execute(
                "UPDATE summaries SET state='completed', content=?, model=?, completed_at=? "
                "WHERE id=?",
                (content.model_dump_json(), model, _iso(utcnow()), summary_id),
            )

    def fail_summary(self, summary_id: str, reason: str) -> None:
        with self._lock, self._db:
            self._db.execute(
                "UPDATE summaries SET state='failed', failure_reason=? WHERE id=?",
                (reason, summary_id),
            )

    def create_conversation(self, c: Conversation) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO conversations VALUES (?,?,?)",
                (c.id, _iso(c.created_at), int(c.born_live)),
            )
            for sid in c.session_ids:
                self._db.execute("INSERT INTO conversation_sessions VALUES (?,?)", (c.id, sid))

    def create_turn(self, t: ConversationTurn, task: AssistantTask) -> ConversationTurn:
        with self._lock, self._db:
            row = self._db.execute(
                "SELECT COALESCE(MAX(seq), -1) + 1 AS n FROM conversation_turns "
                "WHERE conversation_id=?",
                (t.conversation_id,),
            ).fetchone()
            t = t.model_copy(update={"seq": int(row["n"])})
            self._db.execute(
                "INSERT INTO conversation_turns VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    t.id,
                    t.conversation_id,
                    t.seq,
                    t.question,
                    t.answer,
                    json.dumps([c.model_dump() for c in t.citations]),
                    t.watermark,
                    t.state.value,
                    _iso(t.asked_at),
                    _iso(t.completed_at),
                ),
            )
            self._insert_task(task)
        return t

    def append_answer_text(self, turn_id: str, text: str) -> None:
        with self._lock, self._db:
            self._db.execute(
                "UPDATE conversation_turns SET answer = answer || ? WHERE id=?",
                (text, turn_id),
            )

    def finish_turn(
        self, turn_id: str, state: TurnState, citations: list[Citation], watermark: str | None
    ) -> None:
        with self._lock, self._db:
            self._db.execute(
                "UPDATE conversation_turns SET state=?, citations=?, watermark=?, "
                "completed_at=? WHERE id=?",
                (
                    state.value,
                    json.dumps([c.model_dump() for c in citations]),
                    watermark,
                    _iso(utcnow()),
                    turn_id,
                ),
            )

    def set_turn_answer(self, turn_id: str, answer: str) -> None:
        """Replace the accumulated answer with the cleaned/validated text."""
        with self._lock, self._db:
            self._db.execute("UPDATE conversation_turns SET answer=? WHERE id=?", (answer, turn_id))

    def update_task(self, task_id: str, **fields) -> None:
        allowed = {"state", "started_at", "ended_at", "failure_reason"}
        cols, vals = [], []
        for k, v in fields.items():
            if k not in allowed:
                raise ValueError(f"unknown task field {k}")
            if isinstance(v, datetime):
                v = _iso(v)
            elif isinstance(v, TaskState):
                v = v.value
            cols.append(f"{k}=?")
            vals.append(v)
        if not cols:
            return
        with self._lock, self._db:
            self._db.execute(
                f"UPDATE assistant_tasks SET {', '.join(cols)} WHERE id=?",
                (*vals, task_id),
            )

    def _insert_task(self, task: AssistantTask) -> None:
        self._db.execute(
            "INSERT INTO assistant_tasks VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                task.id,
                task.kind.value,
                task.ref_id,
                task.session_id,
                task.priority,
                task.state.value,
                _iso(task.enqueued_at),
                _iso(task.started_at),
                _iso(task.ended_at),
                task.failure_reason,
            ),
        )

    # -- reads -------------------------------------------------------------

    def current_summary(self, session_id: str) -> Summary | None:
        """Newest COMPLETED summary; a pending re-run never displaces a
        readable one (same rule as 002's transcripts). Falls back to the
        newest non-failed so a first-ever pending/failed state is still
        inspectable via GET /summary."""
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM summaries WHERE session_id=? AND state='completed' "
                "ORDER BY created_at DESC, id DESC LIMIT 1",
                (session_id,),
            ).fetchone()
            if row is None:
                row = self._db.execute(
                    "SELECT * FROM summaries WHERE session_id=? AND state != 'failed' "
                    "ORDER BY created_at DESC, id DESC LIMIT 1",
                    (session_id,),
                ).fetchone()
        return self._summary(row) if row else None

    def get_summary(self, summary_id: str) -> Summary | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM summaries WHERE id=?", (summary_id,)).fetchone()
        return self._summary(row) if row else None

    def list_summaries(self, session_id: str) -> list[SummaryVersionInfo]:
        current = self.current_summary(session_id)
        current_completed = current if current and current.state == SummaryState.COMPLETED else None
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM summaries WHERE session_id=? ORDER BY created_at DESC, id DESC",
                (session_id,),
            ).fetchall()
        out = []
        for r in rows:
            superseded = (
                r["state"] == "completed"
                and current_completed is not None
                and r["id"] != current_completed.id
            )
            out.append(
                SummaryVersionInfo(
                    id=r["id"],
                    state=SummaryState(r["state"]),
                    superseded=superseded,
                    model=r["model"],
                    created_at=r["created_at"],
                )
            )
        return out

    def get_conversation(self, cid: str) -> ConversationDetail | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM conversations WHERE id=?", (cid,)).fetchone()
            if row is None:
                return None
            sids = [
                r["session_id"]
                for r in self._db.execute(
                    "SELECT session_id FROM conversation_sessions WHERE conversation_id=?", (cid,)
                )
            ]
            turns = self._db.execute(
                "SELECT * FROM conversation_turns WHERE conversation_id=? ORDER BY seq", (cid,)
            ).fetchall()
        return ConversationDetail(
            id=row["id"],
            session_ids=sids,
            created_at=row["created_at"],
            born_live=bool(row["born_live"]),
            turns=[self._turn_response(t) for t in turns],
        )

    def get_turn(self, turn_id: str) -> ConversationTurn | None:
        with self._lock:
            r = self._db.execute(
                "SELECT * FROM conversation_turns WHERE id=?", (turn_id,)
            ).fetchone()
        if r is None:
            return None
        return ConversationTurn(
            id=r["id"],
            conversation_id=r["conversation_id"],
            seq=r["seq"],
            question=r["question"],
            answer=r["answer"],
            citations=[Citation(**c) for c in json.loads(r["citations"])],
            watermark=r["watermark"],
            state=TurnState(r["state"]),
            asked_at=r["asked_at"],
            completed_at=r["completed_at"],
        )

    def list_conversations(self, session_id: str | None = None) -> list[ConversationResponse]:
        with self._lock:
            if session_id is None:
                rows = self._db.execute(
                    "SELECT * FROM conversations ORDER BY created_at DESC, id DESC"
                ).fetchall()
            else:
                rows = self._db.execute(
                    "SELECT c.* FROM conversations c JOIN conversation_sessions cs "
                    "ON cs.conversation_id = c.id WHERE cs.session_id=? "
                    "ORDER BY c.created_at DESC, c.id DESC",
                    (session_id,),
                ).fetchall()
            out = []
            for r in rows:
                sids = [
                    x["session_id"]
                    for x in self._db.execute(
                        "SELECT session_id FROM conversation_sessions WHERE conversation_id=?",
                        (r["id"],),
                    )
                ]
                out.append(
                    ConversationResponse(
                        id=r["id"],
                        session_ids=sids,
                        created_at=r["created_at"],
                        born_live=bool(r["born_live"]),
                    )
                )
        return out

    def open_tasks(self) -> list[AssistantTask]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM assistant_tasks WHERE state IN ('queued','running')"
            ).fetchall()
        return [self._task(r) for r in rows]

    def next_queued(self) -> AssistantTask | None:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM assistant_tasks WHERE state='queued' "
                "ORDER BY priority, enqueued_at LIMIT 1"
            ).fetchone()
        return self._task(row) if row else None

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _turn_response(r: sqlite3.Row) -> TurnResponse:
        return TurnResponse(
            id=r["id"],
            conversation_id=r["conversation_id"],
            seq=r["seq"],
            question=r["question"],
            answer=r["answer"],
            citations=[Citation(**c) for c in json.loads(r["citations"])],
            watermark=r["watermark"],
            state=TurnState(r["state"]),
            asked_at=r["asked_at"],
            completed_at=r["completed_at"],
        )

    @staticmethod
    def _summary(r: sqlite3.Row) -> Summary:
        return Summary(
            id=r["id"],
            session_id=r["session_id"],
            transcript_id=r["transcript_id"],
            state=SummaryState(r["state"]),
            content=SummaryContent.model_validate_json(r["content"]) if r["content"] else None,
            model=r["model"],
            created_at=r["created_at"],
            completed_at=r["completed_at"],
            failure_reason=r["failure_reason"],
        )

    @staticmethod
    def _task(r: sqlite3.Row) -> AssistantTask:
        return AssistantTask(
            id=r["id"],
            kind=TaskKind(r["kind"]),
            ref_id=r["ref_id"],
            session_id=r["session_id"],
            priority=r["priority"],
            state=TaskState(r["state"]),
            enqueued_at=r["enqueued_at"],
            started_at=r["started_at"],
            ended_at=r["ended_at"],
            failure_reason=r["failure_reason"],
        )


def reconcile_assistant(store: SqliteAssistantStore) -> dict:
    """Startup (research R7): running summaries requeue from scratch;
    running asks fail with the streamed prefix preserved as interrupted."""
    counts = {"requeued": 0, "interrupted": 0}
    for task in store.open_tasks():
        if task.state != TaskState.RUNNING:
            continue
        if task.kind == TaskKind.SUMMARY:
            store.update_task(task.id, state=TaskState.QUEUED, started_at=None)
            counts["requeued"] += 1
        else:
            store.update_task(
                task.id,
                state=TaskState.FAILED,
                ended_at=utcnow(),
                failure_reason="recorder restarted during answer",
            )
            store.finish_turn(task.ref_id, TurnState.INTERRUPTED, [], None)
            counts["interrupted"] += 1
    if any(counts.values()):
        jlog("assistant_reconciled", **counts)
    return counts
