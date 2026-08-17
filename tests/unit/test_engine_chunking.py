from __future__ import annotations

from ambient_recorder.audio.engine import chunk_byte_target
from ambient_recorder.config import CHUNK_SECONDS


def test_chunk_seconds_fixed_by_spec():
    assert CHUNK_SECONDS == 10  # FR-002, Decision Log


def test_native_chunk_byte_math():
    assert chunk_byte_target(48000, 2) == 48000 * 2 * 2 * 10
    assert chunk_byte_target(16000, 1) == 320_000
    assert chunk_byte_target(44100, 1) == 44100 * 2 * 10
