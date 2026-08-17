from __future__ import annotations

import numpy as np

from ambient_recorder.audio.resample import to_pcm16k_mono


def _sine_s16(rate: int, seconds: float, channels: int, freq: float = 440.0) -> bytes:
    t = np.arange(int(rate * seconds)) / rate
    mono = (np.sin(2 * np.pi * freq * t) * 10000).astype(np.int16)
    if channels == 1:
        return mono.tobytes()
    return np.repeat(mono, channels).tobytes()  # interleave identical channels


def test_48k_stereo_one_second_becomes_16k_mono():
    out = to_pcm16k_mono(_sine_s16(48000, 1.0, 2), 48000, 2)
    n_samples = len(out) // 2
    assert abs(n_samples - 16000) <= 16  # resampler edge tolerance
    assert np.abs(np.frombuffer(out, dtype=np.int16)).max() > 5000  # not silence


def test_16k_mono_passthrough_length():
    src = _sine_s16(16000, 0.5, 1)
    out = to_pcm16k_mono(src, 16000, 1)
    assert len(out) == len(src)


def test_downmix_averages_channels():
    left = np.full(1600, 1000, dtype=np.int16)
    right = np.full(1600, 3000, dtype=np.int16)
    interleaved = np.column_stack([left, right]).ravel().tobytes()
    out = np.frombuffer(to_pcm16k_mono(interleaved, 16000, 2), dtype=np.int16)
    assert np.abs(out.astype(int) - 2000).max() <= 1
