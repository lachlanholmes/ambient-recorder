from __future__ import annotations

import errno
import pathlib
import wave

import pytest

from ambient_recorder.models.session import SourceKind
from ambient_recorder.storage.chunks import FsChunkStore
from ambient_recorder.storage.protocols import DiskFullError

PCM_1S = b"\x01\x00" * 16000  # 1 s of 16 kHz mono s16le


def test_write_chunk_is_valid_wav(tmp_path):
    store = FsChunkStore(tmp_path)
    meta = store.write_chunk("sess", SourceKind.MIC, 0, PCM_1S)
    assert meta.seq == 0
    assert meta.duration_s == pytest.approx(1.0)
    with wave.open(meta.file_path, "rb") as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (16000, 1, 2)
        assert w.getnframes() == 16000
    assert meta.size_bytes == pathlib.Path(meta.file_path).stat().st_size


def test_inventory_ordered_and_discards_orphan_part(tmp_path):
    store = FsChunkStore(tmp_path)
    for seq in (0, 1, 2):
        store.write_chunk("sess", SourceKind.SYSTEM, seq, PCM_1S)
    orphan = tmp_path / "sess" / "system" / "chunk_000003.wav.part"
    orphan.write_bytes(b"crashed mid-write")
    found = store.inventory("sess", SourceKind.SYSTEM)
    assert [c.seq for c in found] == [0, 1, 2]
    assert not orphan.exists()


def test_inventory_missing_dir_is_empty(tmp_path):
    assert FsChunkStore(tmp_path).inventory("nope", SourceKind.MIC) == []


def test_empty_chunk_refused(tmp_path):
    with pytest.raises(ValueError):
        FsChunkStore(tmp_path).write_chunk("sess", SourceKind.MIC, 0, b"")


def test_enospc_becomes_disk_full_error(tmp_path, monkeypatch):
    store = FsChunkStore(tmp_path)

    def explode(self, target):
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(pathlib.Path, "replace", explode)
    with pytest.raises(DiskFullError):
        store.write_chunk("sess", SourceKind.MIC, 0, PCM_1S)
    assert list((tmp_path / "sess" / "mic").glob("*.part")) == []  # cleaned up
