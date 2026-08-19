"""US2: startup reconciliation finalises crash-abandoned sessions (T022)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from ambient_recorder.main import create_app
from ambient_recorder.models.session import (
    AudioChunk,
    CaptureSource,
    Session,
    SourceKind,
    utcnow,
)
from ambient_recorder.storage.chunks import FsChunkStore
from ambient_recorder.storage.metadata import SqliteMetadataStore

PCM_10S = b"\x02\x00" * 160_000


def _fabricate_crashed_session(settings) -> str:
    """Simulate a crash: active session row, chunks on disk (one not yet in
    metadata), and a stray .part file."""
    meta = SqliteMetadataStore(settings.db_path)
    chunks = FsChunkStore(settings.sessions_root)
    session = Session(title="crashed", started_at=utcnow(), dir_path="d")
    sources = [
        CaptureSource(
            session_id=session.id,
            kind=k,
            device_id=f"dev-{k}",
            device_label=k.value,
            native_rate_hz=48000,
        )
        for k in SourceKind
    ]
    meta.create_active_session(session, sources)
    for kind in SourceKind:
        for seq in (0, 1, 2):
            written = chunks.write_chunk(session.id, kind, seq, PCM_10S)
            if seq < 2:  # crash lost the DB row for the last finalised chunk
                meta.record_chunk(
                    AudioChunk(
                        session_id=session.id,
                        source_kind=kind,
                        seq=seq,
                        file_path=written.file_path,
                        duration_s=written.duration_s,
                        size_bytes=written.size_bytes,
                    )
                )
    part = settings.sessions_root / session.id / "mic" / "chunk_000003.wav.part"
    part.write_bytes(b"mid-write at crash")
    meta.close()
    return session.id


def test_reconciliation_finalises_interrupted(settings, fake_provider, enumerator):
    sid = _fabricate_crashed_session(settings)
    with TestClient(create_app(settings, fake_provider, enumerator)) as client:
        detail = client.get(f"/sessions/{sid}").json()
        assert detail["status"] == "interrupted"
        assert detail["duration_s"] == 30.0  # from chunk audio on disk
        assert detail["chunk_counts"] == {"mic": 3, "system": 3}  # lost row re-recorded
        assert [e["type"] for e in detail["events"]] == ["reconciled"]
        part = settings.sessions_root / sid / "mic" / "chunk_000003.wav.part"
        assert not part.exists()
        # New sessions can start immediately after reconciliation.
        assert client.post("/sessions", json={}).status_code == 201


def test_reconciliation_is_idempotent(settings, fake_provider, enumerator):
    sid = _fabricate_crashed_session(settings)
    for _ in range(2):  # boot twice
        with TestClient(create_app(settings, fake_provider, enumerator)) as client:
            detail = client.get(f"/sessions/{sid}").json()
    assert detail["status"] == "interrupted"
    assert detail["chunk_counts"] == {"mic": 3, "system": 3}
    assert [e["type"] for e in detail["events"]] == ["reconciled"]  # exactly one


def test_boot_with_nothing_to_reconcile_is_noop(client):
    assert client.get("/sessions").json()["sessions"] == []
