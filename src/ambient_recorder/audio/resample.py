"""Native-rate capture → persisted 16 kHz mono s16le (research R2)."""

from __future__ import annotations

import numpy as np
import soxr

from ambient_recorder.models.session import PERSISTED_SAMPLE_RATE


def to_pcm16k_mono(raw: bytes, native_rate_hz: int, channels: int) -> bytes:
    """Downmix (channel average) and resample interleaved s16le audio."""
    if channels < 1:
        raise ValueError("channels must be >= 1")
    samples = np.frombuffer(raw, dtype=np.int16)
    if channels > 1:
        usable = len(samples) - (len(samples) % channels)
        samples = samples[:usable].reshape(-1, channels).mean(axis=1)
    audio = samples.astype(np.float32) / 32768.0
    if native_rate_hz != PERSISTED_SAMPLE_RATE:
        audio = soxr.resample(audio, native_rate_hz, PERSISTED_SAMPLE_RATE, quality="VHQ")
    out = np.clip(audio * 32768.0, -32768, 32767).astype(np.int16)
    return out.tobytes()
