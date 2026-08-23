"""T010: seq assignment, current selection, supersede-by-insert."""

from __future__ import annotations

import pytest

from ambient_recorder.models.session import utcnow
from ambient_recorder.models.transcript import (
    JobState,
    NewSegment,
    Speaker,
    Transcript,
    TranscriptionJob,
    TranscriptMode,
    TranscriptState,
)
from ambient_recorder.storage.transcripts import SqliteTranscriptStore, reconcile_transcription


@pytest.fixture
def store(tmp_path):
    s = SqliteTranscriptStore(tmp_path / "t.sqlite3")
    yield s
    s.close()


def _mk(
    store,
    session="s",
    mode=TranscriptMode.LIVE,
    state=TranscriptState.LIVE,
    job_state=JobState.RUNNING,
) -> Transcript:
    t = Transcript(session_id=session, mode=mode, state=state)
    store.create_transcript(
        t,
        TranscriptionJob(
            transcript_id=t.id,
            session_id=session,
            mode=mode,
            state=job_state,
            priority=0 if mode == TranscriptMode.LIVE else 1,
        ),
    )
    return t


def test_seq_monotonic_and_segments_after(store):
    t = _mk(store)
    for i in range(3):
        seg = store.append_segment(
            t.id, NewSegment(source=Speaker.ME, start_s=i, end_s=i + 1, text=f"w{i}")
        )
        assert seg.seq == i
    assert [s.seq for s in store.segments_after(t.id, 0)] == [1, 2]
    assert [s.seq for s in store.segments_after(t.id, -1)] == [0, 1, 2]


def test_current_ignores_pending_and_failed(store):
    live = _mk(store)
    store.set_state(live.id, TranscriptState.COMPLETED, final=True, finalised_at=utcnow())
    pending = _mk(
        store,
        mode=TranscriptMode.ON_DEMAND,
        state=TranscriptState.PENDING,
        job_state=JobState.QUEUED,
    )
    assert store.current_transcript("s").id == live.id  # pending does not displace
    assert store.pending_transcript("s").id == pending.id
    store.set_state(pending.id, TranscriptState.FAILED, failure_reason="boom")
    assert store.current_transcript("s").id == live.id  # failed never displaces
    ok = _mk(
        store,
        mode=TranscriptMode.ON_DEMAND,
        state=TranscriptState.PENDING,
        job_state=JobState.QUEUED,
    )
    store.set_state(ok.id, TranscriptState.COMPLETED, final=True, finalised_at=utcnow())
    assert store.current_transcript("s").id == ok.id  # success supersedes
    summaries = store.list_transcripts("s")
    by_id = {x.id: x for x in summaries}
    assert by_id[live.id].superseded is True
    assert by_id[ok.id].superseded is False
    assert by_id[pending.id].superseded is False  # failed attempts are not "superseded"


def test_reconcile_orphans(store):
    live = _mk(store)  # running live, session gone at boot
    od = _mk(
        store,
        mode=TranscriptMode.ON_DEMAND,
        state=TranscriptState.PENDING,
        job_state=JobState.RUNNING,
    )
    store.update_job(od.id, progress_chunks=7)
    counts = reconcile_transcription(store, active_session_id=None)
    assert counts == {"interrupted_live": 1, "requeued": 1}
    assert store.get_transcript(live.id).state == TranscriptState.INTERRUPTED_LIVE
    j = store.get_job(od.id)
    assert j.state == JobState.QUEUED and j.progress_chunks == 0
    assert reconcile_transcription(store, None) == {
        "interrupted_live": 0,
        "requeued": 1,
    }  # idempotent-ish: queued stays queued
