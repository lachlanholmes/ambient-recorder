from __future__ import annotations

import pytest

from ambient_recorder.models.session import (
    AudioChunk,
    CaptureSource,
    Session,
    SourceKind,
    utcnow,
)
from ambient_recorder.storage.metadata import SqliteMetadataStore
from ambient_recorder.storage.protocols import ActiveSessionExistsError


@pytest.fixture
def store(tmp_path):
    s = SqliteMetadataStore(tmp_path / "meta.sqlite3")
    yield s
    s.close()


def _session(title=None) -> tuple[Session, list[CaptureSource]]:
    s = Session(title=title, started_at=utcnow(), dir_path="d")
    sources = [
        CaptureSource(session_id=s.id, kind=k, device_id=f"dev-{k}",
                      device_label=k.value, native_rate_hz=48000)
        for k in SourceKind
    ]
    return s, sources


def test_one_active_session_enforced(store):
    a, sa = _session()
    store.create_active_session(a, sa)
    b, sb = _session()
    with pytest.raises(ActiveSessionExistsError) as e:
        store.create_active_session(b, sb)
    assert e.value.active_id == a.id


def test_record_chunk_idempotent_and_counts(store):
    s, sources = _session()
    store.create_active_session(s, sources)
    chunk = AudioChunk(session_id=s.id, source_kind=SourceKind.MIC, seq=0,
                       file_path="p", duration_s=10.0, size_bytes=320044)
    store.record_chunk(chunk)
    store.record_chunk(chunk)  # reconciliation may re-record
    detail = store.get_session(s.id)
    assert detail.chunk_counts[SourceKind.MIC] == 1
    assert detail.size_bytes == 320044


def test_finalize_and_end_source(store):
    s, sources = _session()
    store.create_active_session(s, sources)
    now = utcnow()
    store.end_source(s.id, SourceKind.MIC, "ended_device_lost", now)
    store.end_source(s.id, SourceKind.SYSTEM, "completed", now)
    store.finalize_session(s.id, "completed", now, 42.5)
    detail = store.get_session(s.id)
    assert detail.status == "completed"
    assert detail.duration_s == 42.5
    statuses = {src.kind: src.status for src in detail.sources}
    assert statuses[SourceKind.MIC] == "ended_device_lost"
    assert statuses[SourceKind.SYSTEM] == "completed"
    assert store.active_sessions() == []


def test_last_device_ids_from_most_recent_session(store):
    a, sa = _session("first")
    store.create_active_session(a, sa)
    store.finalize_session(a.id, "completed", utcnow(), 1.0)
    b = Session(title="second", started_at=utcnow(), dir_path="d")
    sb = [CaptureSource(session_id=b.id, kind=k, device_id=f"new-{k}",
                        device_label=k.value, native_rate_hz=48000)
          for k in SourceKind]
    store.create_active_session(b, sb)
    store.finalize_session(b.id, "completed", utcnow(), 1.0)
    assert store.last_device_ids() == {
        SourceKind.MIC: "new-mic", SourceKind.SYSTEM: "new-system"
    }


def test_list_sessions_newest_first(store):
    a, sa = _session("a")
    store.create_active_session(a, sa)
    store.finalize_session(a.id, "completed", utcnow(), 1.0)
    b, sb = _session("b")
    store.create_active_session(b, sb)
    listed = store.list_sessions()
    assert [x.id for x in listed] == [b.id, a.id]
