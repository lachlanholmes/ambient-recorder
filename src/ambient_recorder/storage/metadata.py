"""SQLite metadata store (research R4) + startup reconciliation (R5).

Single-connection, lock-serialised writes; WAL mode. Chunk files on disk
are the source of truth — reconciliation derives metadata from them.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Literal

from ambient_recorder.logging import jlog
from ambient_recorder.models.api import CaptureSourceInfo, SessionDetail, SessionSummary
from ambient_recorder.models.session import (
    AudioChunk,
    CaptureSource,
    EventType,
    Session,
    SessionEvent,
    SessionStatus,
    SourceKind,
    SourceStatus,
    utcnow,
)
from ambient_recorder.storage.protocols import ActiveSessionExistsError, ChunkStore

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    title TEXT,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    duration_s REAL,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    dir_path TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS one_active ON sessions(status) WHERE status = 'active';
CREATE TABLE IF NOT EXISTS capture_sources (
    session_id TEXT NOT NULL REFERENCES sessions(id),
    kind TEXT NOT NULL,
    device_id TEXT NOT NULL,
    device_label TEXT NOT NULL,
    native_rate_hz INTEGER NOT NULL,
    persisted_format TEXT NOT NULL,
    status TEXT NOT NULL,
    ended_at TEXT,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (session_id, kind)
);
CREATE TABLE IF NOT EXISTS audio_chunks (
    session_id TEXT NOT NULL REFERENCES sessions(id),
    source_kind TEXT NOT NULL,
    seq INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    duration_s REAL NOT NULL,
    size_bytes INTEGER NOT NULL,
    written_at TEXT NOT NULL,
    PRIMARY KEY (session_id, source_kind, seq)
);
CREATE TABLE IF NOT EXISTS session_events (
    session_id TEXT NOT NULL REFERENCES sessions(id),
    at TEXT NOT NULL,
    type TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '{}'
);
"""


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


class SqliteMetadataStore:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(db_path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock, self._db:
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA foreign_keys=ON")
            self._db.executescript(_SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # -- writes ----------------------------------------------------------

    def create_active_session(self, session: Session, sources: list[CaptureSource]) -> None:
        with self._lock:
            try:
                with self._db:
                    self._db.execute(
                        "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?)",
                        (
                            session.id,
                            session.title,
                            session.status.value,
                            _iso(session.started_at),
                            _iso(session.ended_at),
                            session.duration_s,
                            session.size_bytes,
                            session.dir_path,
                            _iso(session.created_at),
                        ),
                    )
                    for s in sources:
                        self._db.execute(
                            "INSERT INTO capture_sources VALUES (?,?,?,?,?,?,?,?,?)",
                            (
                                s.session_id,
                                s.kind.value,
                                s.device_id,
                                s.device_label,
                                s.native_rate_hz,
                                s.persisted_format,
                                s.status.value,
                                _iso(s.ended_at),
                                s.chunk_count,
                            ),
                        )
            except sqlite3.IntegrityError as e:
                if "one_active" in str(e) or "sessions.status" in str(e):
                    row = self._db.execute(
                        "SELECT id FROM sessions WHERE status='active'"
                    ).fetchone()
                    raise ActiveSessionExistsError(row["id"] if row else "?") from e
                raise

    def record_chunk(self, chunk: AudioChunk) -> None:
        with self._lock, self._db:
            cur = self._db.execute(
                "INSERT OR IGNORE INTO audio_chunks VALUES (?,?,?,?,?,?,?)",
                (
                    chunk.session_id,
                    chunk.source_kind.value,
                    chunk.seq,
                    chunk.file_path,
                    chunk.duration_s,
                    chunk.size_bytes,
                    _iso(chunk.written_at),
                ),
            )
            if cur.rowcount:
                self._db.execute(
                    "UPDATE capture_sources SET chunk_count = chunk_count + 1 "
                    "WHERE session_id=? AND kind=?",
                    (chunk.session_id, chunk.source_kind.value),
                )
                self._db.execute(
                    "UPDATE sessions SET size_bytes = size_bytes + ? WHERE id=?",
                    (chunk.size_bytes, chunk.session_id),
                )

    def end_source(
        self,
        session_id: str,
        kind: SourceKind,
        status: Literal["completed", "ended_device_lost"],
        ended_at: datetime,
    ) -> None:
        with self._lock, self._db:
            self._db.execute(
                "UPDATE capture_sources SET status=?, ended_at=? "
                "WHERE session_id=? AND kind=? AND status='active'",
                (status, _iso(ended_at), session_id, kind.value),
            )

    def append_event(self, event: SessionEvent) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO session_events VALUES (?,?,?,?)",
                (
                    event.session_id,
                    _iso(event.at),
                    event.type.value,
                    json.dumps(event.detail, default=str),
                ),
            )

    def finalize_session(
        self,
        session_id: str,
        status: Literal["completed", "interrupted"],
        ended_at: datetime,
        duration_s: float,
    ) -> None:
        with self._lock, self._db:
            self._db.execute(
                "UPDATE sessions SET status=?, ended_at=?, duration_s=? "
                "WHERE id=? AND status='active'",
                (status, _iso(ended_at), duration_s, session_id),
            )

    # -- reads -----------------------------------------------------------

    def list_sessions(self) -> list[SessionSummary]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM sessions ORDER BY started_at DESC, id DESC"
            ).fetchall()
        return [self._summary(r) for r in rows]

    def get_session(self, session_id: str) -> SessionDetail | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
            if row is None:
                return None
            sources = self._db.execute(
                "SELECT * FROM capture_sources WHERE session_id=? ORDER BY kind",
                (session_id,),
            ).fetchall()
            events = self._db.execute(
                "SELECT * FROM session_events WHERE session_id=? ORDER BY at, rowid",
                (session_id,),
            ).fetchall()
        return SessionDetail(
            **self._summary(row).model_dump(),
            sources=[
                CaptureSourceInfo(
                    kind=SourceKind(s["kind"]),
                    device_id=s["device_id"],
                    device_label=s["device_label"],
                    native_rate_hz=s["native_rate_hz"],
                    persisted_format=s["persisted_format"],
                    status=SourceStatus(s["status"]),
                    ended_at=s["ended_at"],
                    chunk_count=s["chunk_count"],
                )
                for s in sources
            ],
            events=[
                SessionEvent(
                    session_id=e["session_id"],
                    at=e["at"],
                    type=EventType(e["type"]),
                    detail=json.loads(e["detail"]),
                )
                for e in events
            ],
            chunk_counts={SourceKind(s["kind"]): s["chunk_count"] for s in sources},
        )

    def active_sessions(self) -> list[Session]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM sessions WHERE status='active'").fetchall()
        return [
            Session(
                id=r["id"],
                title=r["title"],
                status=SessionStatus(r["status"]),
                started_at=r["started_at"],
                ended_at=r["ended_at"],
                duration_s=r["duration_s"],
                size_bytes=r["size_bytes"],
                dir_path=r["dir_path"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def last_device_ids(self) -> dict[SourceKind, str]:
        with self._lock:
            rows = self._db.execute(
                "SELECT cs.kind, cs.device_id FROM capture_sources cs "
                "JOIN sessions s ON s.id = cs.session_id "
                "ORDER BY s.started_at DESC, s.id DESC LIMIT 2"
            ).fetchall()
        return {SourceKind(r["kind"]): r["device_id"] for r in rows}

    def _summary(self, r: sqlite3.Row) -> SessionSummary:
        return SessionSummary(
            id=r["id"],
            title=r["title"],
            status=SessionStatus(r["status"]),
            started_at=r["started_at"],
            ended_at=r["ended_at"],
            duration_s=r["duration_s"],
            size_bytes=r["size_bytes"],
        )


def reconcile_interrupted(meta: SqliteMetadataStore, chunks: ChunkStore) -> int:
    """FR-008 / research R5: finalise sessions left active by a crash.

    Chunk files are truth: re-record any rows the crash lost, discard
    .part orphans (inventory does), recompute duration from audio length.
    Idempotent; a no-active-session boot is a silent no-op. Returns the
    number of sessions reconciled.
    """
    count = 0
    for session in meta.active_sessions():
        durations: dict[SourceKind, float] = {}
        for kind in SourceKind:
            found = chunks.inventory(session.id, kind)
            for c in found:
                meta.record_chunk(
                    AudioChunk(
                        session_id=session.id,
                        source_kind=kind,
                        seq=c.seq,
                        file_path=c.file_path,
                        duration_s=c.duration_s,
                        size_bytes=c.size_bytes,
                    )
                )
            durations[kind] = sum(c.duration_s for c in found)
            meta.end_source(session.id, kind, "completed", utcnow())
        duration = max(durations.values(), default=0.0)
        meta.finalize_session(session.id, "interrupted", utcnow(), duration)
        meta.append_event(
            SessionEvent(
                session_id=session.id,
                type=EventType.RECONCILED,
                detail={"chunk_durations_s": {k.value: v for k, v in durations.items()}},
            )
        )
        jlog("session_reconciled", session_id=session.id, duration_s=duration)
        count += 1
    return count
