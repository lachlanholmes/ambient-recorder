"""Atomic WAV chunk store (research R3).

Each chunk is a self-contained WAV written to `<name>.part` and renamed
into place; a crash leaves at most one .part per source, which
inventory() discards. Chunk rows enter metadata only after the rename.
"""

from __future__ import annotations

import errno
import re
import wave
from pathlib import Path

from ambient_recorder.models.session import (
    PERSISTED_CHANNELS,
    PERSISTED_SAMPLE_RATE,
    PERSISTED_SAMPLE_WIDTH,
    SourceKind,
)
from ambient_recorder.storage.protocols import ChunkMeta, DiskFullError

_CHUNK_RE = re.compile(r"^chunk_(\d{6})\.wav$")


class FsChunkStore:
    def __init__(self, sessions_root: Path):
        self._root = Path(sessions_root)

    def _source_dir(self, session_id: str, kind: SourceKind) -> Path:
        return self._root / session_id / kind.value

    def write_chunk(
        self, session_id: str, kind: SourceKind, seq: int, pcm16k_mono: bytes
    ) -> ChunkMeta:
        if not pcm16k_mono:
            raise ValueError("refusing to write an empty chunk")
        target = self._source_dir(session_id, kind) / f"chunk_{seq:06d}.wav"
        part = target.with_suffix(".wav.part")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with wave.open(str(part), "wb") as w:
                w.setnchannels(PERSISTED_CHANNELS)
                w.setsampwidth(PERSISTED_SAMPLE_WIDTH)
                w.setframerate(PERSISTED_SAMPLE_RATE)
                w.writeframes(pcm16k_mono)
            part.replace(target)
        except OSError as e:
            part.unlink(missing_ok=True)
            if e.errno == errno.ENOSPC:
                raise DiskFullError(str(target)) from e
            raise
        frames = len(pcm16k_mono) // PERSISTED_SAMPLE_WIDTH
        return ChunkMeta(
            file_path=str(target),
            seq=seq,
            duration_s=frames / PERSISTED_SAMPLE_RATE,
            size_bytes=target.stat().st_size,
        )

    def inventory(self, session_id: str, kind: SourceKind) -> list[ChunkMeta]:
        d = self._source_dir(session_id, kind)
        if not d.is_dir():
            return []
        for orphan in d.glob("*.part"):
            orphan.unlink(missing_ok=True)
        out: list[ChunkMeta] = []
        for f in sorted(d.iterdir()):
            m = _CHUNK_RE.match(f.name)
            if not m:
                continue
            with wave.open(str(f), "rb") as w:
                duration = w.getnframes() / w.getframerate()
            out.append(
                ChunkMeta(
                    file_path=str(f),
                    seq=int(m.group(1)),
                    duration_s=duration,
                    size_bytes=f.stat().st_size,
                )
            )
        return out
