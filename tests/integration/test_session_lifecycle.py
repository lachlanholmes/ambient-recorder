"""US1 end-to-end with the fake provider (T018)."""

from __future__ import annotations

import wave
from pathlib import Path

import pytest
from tests.support.fake_capture import MIC_ID, SYSTEM_ID

from ambient_recorder.models.api import SessionDetail
from ambient_recorder.models.session import SourceKind
from ambient_recorder.storage.chunks import FsChunkStore


def test_full_lifecycle_chunks_metadata_duration(client, fake_provider, settings):
    sid = client.post("/sessions", json={"title": "lifecycle"}).json()["id"]
    fake_provider.push_seconds(MIC_ID, 35.0)      # 3 full chunks + 5 s partial
    fake_provider.push_seconds(SYSTEM_ID, 35.0)
    detail = SessionDetail.model_validate(
        client.post(f"/sessions/{sid}/stop").json()
    )

    assert detail.status == "completed"
    # Duration derives from audio length (35 s), never wall clock (~ms).
    assert detail.duration_s == pytest.approx(35.0, abs=0.1)
    assert detail.chunk_counts[SourceKind.MIC] == 4
    assert detail.chunk_counts[SourceKind.SYSTEM] == 4

    # Sources separable on disk; every chunk individually a valid WAV.
    store = FsChunkStore(settings.sessions_root)
    for kind in SourceKind:
        found = store.inventory(sid, kind)
        assert [c.seq for c in found] == [0, 1, 2, 3]
        durations = []
        for c in found:
            with wave.open(c.file_path, "rb") as w:
                assert (w.getframerate(), w.getnchannels()) == (16000, 1)
                durations.append(w.getnframes() / w.getframerate())
        assert sum(durations) == pytest.approx(35.0, abs=0.1)
        assert durations[:3] == pytest.approx([10.0, 10.0, 10.0], abs=0.01)

    # Metadata matches disk inventory.
    assert detail.size_bytes == sum(
        c.size_bytes for kind in SourceKind for c in store.inventory(sid, kind)
    )
    mic_dir = Path(settings.sessions_root) / sid / "mic"
    assert not list(mic_dir.glob("*.part"))
