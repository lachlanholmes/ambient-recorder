"""SQLite TranscriptStore (research R7) + transcription startup reconciliation.

Shares feature 001's database file. Insert-only transcript versioning;
"current" = newest transcript that is neither failed nor pending. The
transcription worker is the only writer of these tables.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from ambient_recorder.logging import jlog
from ambient_recorder.models.session import utcnow
from ambient_recorder.models.transcript import (
    JobState,
    NewSegment,
    Speaker,
    Transcript,
    TranscriptionJob,
    TranscriptMode,
    TranscriptSegment,
    TranscriptState,
    TranscriptSummary,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS transcripts (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    mode TEXT NOT NULL,
    state TEXT NOT NULL,
    final INTEGER NOT NULL DEFAULT 0,
    engine TEXT,
    model TEXT,
    created_at TEXT NOT NULL,
    finalised_at TEXT,
    failure_reason TEXT
);
CREATE INDEX IF NOT EXISTS transcripts_by_session ON transcripts(session_id, created_at DESC);
CREATE TABLE IF NOT EXISTS transcript_segments (
    transcript_id TEXT NOT NULL REFERENCES transcripts(id),
    seq INTEGER NOT NULL,
    source TEXT NOT NULL,
    start_s REAL NOT NULL,
    end_s REAL NOT NULL,
    text TEXT NOT NULL,
    PRIMARY KEY (transcript_id, seq)
);
CREATE TABLE IF NOT EXISTS transcription_jobs (
    transcript_id TEXT PRIMARY KEY REFERENCES transcripts(id),
    session_id TEXT NOT NULL,
    mode TEXT NOT NULL,
    state TEXT NOT NULL,
    priority INTEGER NOT NULL,
    progress_chunks INTEGER NOT NULL DEFAULT 0,
    total_chunks INTEGER,
    lag_s REAL,
    enqueued_at TEXT NOT NULL,
    started_at TEXT,
    ended_at TEXT,
    failure_reason TEXT
);
"""

_NON_CURRENT = ("failed", "pending")


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


class SqliteTranscriptStore:
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

    def create_transcript(self, t: Transcript, job: TranscriptionJob) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO transcripts VALUES (?,?,?,?,?,?,?,?,?,?)",
                (t.id, t.session_id, t.mode.value, t.state.value, int(t.final), t.engine,
                 t.model, _iso(t.created_at), _iso(t.finalised_at), t.failure_reason),
            )
            self._db.execute(
                "INSERT INTO transcription_jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (job.transcript_id, job.session_id, job.mode.value, job.state.value,
                 job.priority, job.progress_chunks, job.total_chunks, job.lag_s,
                 _iso(job.enqueued_at), _iso(job.started_at), _iso(job.ended_at),
                 job.failure_reason),
            )

    def append_segment(self, transcript_id: str, seg: NewSegment) -> TranscriptSegment:
        with self._lock, self._db:
            row = self._db.execute(
                "SELECT COALESCE(MAX(seq), -1) + 1 AS n FROM transcript_segments "
                "WHERE transcript_id=?", (transcript_id,)
            ).fetchone()
            seq = int(row["n"])
            self._db.execute(
                "INSERT INTO transcript_segments VALUES (?,?,?,?,?,?)",
                (transcript_id, seq, seg.source.value, seg.start_s, seg.end_s, seg.text.strip()),
            )
        return TranscriptSegment(transcript_id=transcript_id, seq=seq, source=seg.source,
                                 start_s=seg.start_s, end_s=seg.end_s, text=seg.text)

    def update_job(self, transcript_id: str, **fields) -> None:
        allowed = {"state", "progress_chunks", "total_chunks", "lag_s",
                   "started_at", "ended_at", "failure_reason"}
        cols, vals = [], []
        for k, v in fields.items():
            if k not in allowed:
                raise ValueError(f"unknown job field {k}")
            if isinstance(v, datetime):
                v = _iso(v)
            elif isinstance(v, JobState):
                v = v.value
            cols.append(f"{k}=?")
            vals.append(v)
        if not cols:
            return
        with self._lock, self._db:
            self._db.execute(
                f"UPDATE transcription_jobs SET {', '.join(cols)} WHERE transcript_id=?",
                (*vals, transcript_id),
            )

    def set_state(self, transcript_id: str, state: TranscriptState, *, final: bool = False,
                  failure_reason: str | None = None, finalised_at: datetime | None = None,
                  ) -> None:
        with self._lock, self._db:
            self._db.execute(
                "UPDATE transcripts SET state=?, final=?, failure_reason=?, "
                "finalised_at=COALESCE(?, finalised_at) WHERE id=?",
                (state.value, int(final), failure_reason, _iso(finalised_at), transcript_id),
            )

    def set_engine(self, transcript_id: str, engine: str, model: str) -> None:
        with self._lock, self._db:
            self._db.execute("UPDATE transcripts SET engine=?, model=? WHERE id=?",
                             (engine, model, transcript_id))

    # -- reads -------------------------------------------------------------

    def current_transcript(self, session_id: str) -> Transcript | None:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM transcripts WHERE session_id=? AND state NOT IN (?,?) "
                "ORDER BY created_at DESC, id DESC LIMIT 1",
                (session_id, *_NON_CURRENT),
            ).fetchone()
        return self._t(row) if row else None

    def pending_transcript(self, session_id: str) -> Transcript | None:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM transcripts WHERE session_id=? AND state='pending' "
                "ORDER BY created_at DESC LIMIT 1", (session_id,)
            ).fetchone()
        return self._t(row) if row else None

    def list_transcripts(self, session_id: str) -> list[TranscriptSummary]:
        current = self.current_transcript(session_id)
        with self._lock:
            rows = self._db.execute(
                "SELECT t.*, (SELECT COUNT(*) FROM transcript_segments s "
                " WHERE s.transcript_id=t.id) AS n FROM transcripts t "
                "WHERE session_id=? ORDER BY created_at DESC, id DESC", (session_id,)
            ).fetchall()
        out = []
        for r in rows:
            t = self._t(r)
            superseded = (t.state not in (TranscriptState.FAILED, TranscriptState.PENDING)
                          and current is not None and t.id != current.id)
            out.append(TranscriptSummary(
                id=t.id, mode=t.mode, state=t.state, final=t.final, superseded=superseded,
                model=t.model, created_at=t.created_at, finalised_at=t.finalised_at,
                segment_count=int(r["n"]),
            ))
        return out

    def get_transcript(self, transcript_id: str) -> Transcript | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM transcripts WHERE id=?",
                                   (transcript_id,)).fetchone()
        return self._t(row) if row else None

    def get_job(self, transcript_id: str) -> TranscriptionJob | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM transcription_jobs WHERE transcript_id=?",
                                   (transcript_id,)).fetchone()
        return self._j(row) if row else None

    def segments_after(self, transcript_id: str, after: int) -> list[TranscriptSegment]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM transcript_segments WHERE transcript_id=? AND seq>? "
                "ORDER BY seq", (transcript_id, after)
            ).fetchall()
        return [TranscriptSegment(transcript_id=r["transcript_id"], seq=r["seq"],
                                  source=Speaker(r["source"]), start_s=r["start_s"],
                                  end_s=r["end_s"], text=r["text"]) for r in rows]

    def open_jobs(self) -> list[TranscriptionJob]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM transcription_jobs WHERE state IN ('queued','running','finalising')"
            ).fetchall()
        return [self._j(r) for r in rows]

    def next_queued(self) -> TranscriptionJob | None:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM transcription_jobs WHERE state='queued' "
                "ORDER BY priority, enqueued_at LIMIT 1"
            ).fetchone()
        return self._j(row) if row else None

    def running_on_demand(self, session_id: str) -> TranscriptionJob | None:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM transcription_jobs WHERE session_id=? AND mode='on_demand' "
                "AND state IN ('queued','running') LIMIT 1", (session_id,)
            ).fetchone()
        return self._j(row) if row else None

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _t(r: sqlite3.Row) -> Transcript:
        return Transcript(id=r["id"], session_id=r["session_id"], mode=TranscriptMode(r["mode"]),
                          state=TranscriptState(r["state"]), final=bool(r["final"]),
                          engine=r["engine"], model=r["model"], created_at=r["created_at"],
                          finalised_at=r["finalised_at"], failure_reason=r["failure_reason"])

    @staticmethod
    def _j(r: sqlite3.Row) -> TranscriptionJob:
        return TranscriptionJob(transcript_id=r["transcript_id"], session_id=r["session_id"],
                                mode=TranscriptMode(r["mode"]), state=JobState(r["state"]),
                                priority=r["priority"], progress_chunks=r["progress_chunks"],
                                total_chunks=r["total_chunks"], lag_s=r["lag_s"],
                                enqueued_at=r["enqueued_at"], started_at=r["started_at"],
                                ended_at=r["ended_at"], failure_reason=r["failure_reason"])


def reconcile_transcription(store: SqliteTranscriptStore, active_session_id: str | None) -> dict:
    """Startup (research R7): orphaned live → interrupted_live (segments kept);
    orphaned running on-demand → requeued. Idempotent."""
    counts = {"interrupted_live": 0, "requeued": 0}
    for job in store.open_jobs():
        if job.mode == TranscriptMode.LIVE:
            if job.session_id == active_session_id:
                continue  # can't happen at boot, defensive
            store.set_state(job.transcript_id, TranscriptState.INTERRUPTED_LIVE)
            store.update_job(job.transcript_id, state=JobState.FAILED, ended_at=utcnow(),
                             failure_reason="recorder restarted during live transcription")
            counts["interrupted_live"] += 1
        else:
            store.update_job(job.transcript_id, state=JobState.QUEUED, started_at=None,
                             progress_chunks=0)
            counts["requeued"] += 1
    if any(counts.values()):
        jlog("transcription_reconciled", **counts)
    return counts
