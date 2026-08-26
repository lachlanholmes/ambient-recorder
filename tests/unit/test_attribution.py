"""T011: EnergyBuffer + bleed rule, pure and model-free."""

from __future__ import annotations

import numpy as np
import pytest

from ambient_recorder.models.session import SourceKind
from ambient_recorder.transcription.attribution import (
    AttributionConfig,
    EnergyBuffer,
    TimedSegment,
    attribute,
)

MIC, SYS = SourceKind.MIC, SourceKind.SYSTEM


def tone(seconds: float, amplitude: int) -> bytes:
    n = int(16000 * seconds)
    return (np.full(n, amplitude, dtype=np.int16)).tobytes()


def _buf(mic_amp: int, sys_amp: int, seconds: float = 10.0) -> EnergyBuffer:
    e = EnergyBuffer()
    e.add(MIC, 0.0, tone(seconds, mic_amp))
    e.add(SYS, 0.0, tone(seconds, sys_amp))
    return e


def test_rms_db_and_coverage():
    e = EnergyBuffer()
    e.add(MIC, 0.0, tone(10.0, 3277))  # ≈ -20 dBFS
    assert e.rms_db(MIC, 1.0, 2.0) == pytest.approx(-20.0, abs=0.2)
    assert e.rms_db(MIC, 9.5, 10.5) is None  # not covered yet
    assert e.rms_db(SYS, 1.0, 2.0) is None  # other track empty
    e.add(MIC, 10.0, tone(1.0, 3277))
    assert e.rms_db(MIC, 9.5, 10.5) is not None


def test_bleed_dropped_when_system_louder_and_same_words():
    e = _buf(mic_amp=800, sys_amp=6400)  # system +18 dB
    mic = [TimedSegment(1.0, 3.0, "let's push the launch to thursday")]
    sys = [TimedSegment(1.1, 3.1, "let's push the launch to Thursday")]
    out, deferred = attribute(mic, sys, e, AttributionConfig())
    assert [(s.source.value, s.text) for s in out] == [
        ("them", "let's push the launch to Thursday")
    ]
    assert not deferred[MIC] and not deferred[SYS]


def test_genuine_me_kept_when_mic_louder():
    e = _buf(mic_amp=6400, sys_amp=800)
    mic = [TimedSegment(1.0, 3.0, "sounds good to me")]
    sys = [TimedSegment(1.0, 3.0, "sounds good to me")]  # improbable echo, mic wins
    out, _ = attribute(mic, sys, e, AttributionConfig())
    assert [s.source.value for s in out] == ["me"]


def test_overlap_talk_both_kept_when_words_differ():
    e = _buf(mic_amp=800, sys_amp=6400)
    mic = [TimedSegment(1.0, 3.0, "wait I disagree")]
    sys = [TimedSegment(1.0, 3.0, "and the budget is approved")]
    out, _ = attribute(mic, sys, e, AttributionConfig())
    assert sorted(s.source.value for s in out) == ["me", "them"]


def test_threshold_boundary():
    e = _buf(mic_amp=1000, sys_amp=1900)  # ≈ +5.6 dB, under 6 dB
    mic = [TimedSegment(1.0, 3.0, "same words here")]
    sys = [TimedSegment(1.0, 3.0, "same words here")]
    out, _ = attribute(mic, sys, e, AttributionConfig(bleed_db=6.0))
    assert sorted(s.source.value for s in out) == ["me", "them"]  # not confident → keep both
    out, _ = attribute(mic, sys, e, AttributionConfig(bleed_db=5.0))
    assert [s.source.value for s in out] == ["them"]


def test_uncovered_span_is_deferred_then_resolved():
    e = EnergyBuffer()
    e.add(MIC, 0.0, tone(10.0, 800))  # system track hasn't arrived
    mic = [TimedSegment(1.0, 3.0, "hello there")]
    out, deferred = attribute(mic, [], e, AttributionConfig())
    assert out == [] and deferred[MIC] == mic
    e.add(SYS, 0.0, tone(10.0, 100))
    out, deferred = attribute(deferred[MIC], [], e, AttributionConfig())
    assert [s.source.value for s in out] == ["me"] and not deferred[MIC]


def test_field_case_different_segmentation_and_late_other_track():
    """Gate-(c) live run: Whisper split the same bleed audio into different
    segments per track, and the system chunk arrived after the mic chunk."""
    e = _buf(mic_amp=800, sys_amp=8000, seconds=30.0)  # system ≈ +20 dB, as measured
    mic = [
        TimedSegment(
            21.0,
            25.2,
            "You and the AI would would both do it in tandem for a few months and you would be",
        ),
        TimedSegment(
            25.2,
            28.9,
            "like you would get to how much are they catching how much am I catching is it about",
        ),
    ]
    # System track not yet transcribed past 20.9 → both mic candidates defer.
    out, deferred = attribute(
        mic, [], e, AttributionConfig(), transcribed_until={MIC: 30.0, SYS: 20.9}
    )
    assert out == [] and deferred[MIC] == mic
    # System chunk lands with *different* boundaries; merged text matches.
    sys = [
        TimedSegment(
            20.9,
            26.1,
            "You and the AI would would both do it in tandem for a few months "
            "and you would be like you would get to",
        ),
        TimedSegment(
            26.4,
            29.9,
            "How much are they catching how much am I catching is it about the same "
            "is it more is it?",
        ),
    ]
    out, deferred = attribute(
        mic, sys, e, AttributionConfig(), transcribed_until={MIC: 30.0, SYS: 30.0}
    )
    assert [s.source.value for s in out] == ["them", "them"]  # mic copies dropped
    assert not deferred[MIC]


def test_expired_window_emits_instead_of_deferring_forever():
    """Live 2026-08-24: candidates deferred during a slow start became
    permanently unjudgeable once the 30 s window slid past; lag grew
    without bound. Expired spans must emit, not defer."""
    e = EnergyBuffer(window_s=30.0)
    e.add(MIC, 0.0, tone(40.0, 800))  # window now covers 10..40 on mic
    # system track starts late and never covered 2..4
    e.add(SYS, 35.0, tone(5.0, 8000))
    mic = [TimedSegment(2.0, 4.0, "early words the window lost")]
    out, deferred = attribute(mic, [], e, AttributionConfig())
    assert [s.text for s in out] == ["early words the window lost"]
    assert not deferred[MIC]


def test_pending_coverage_still_defers():
    e = EnergyBuffer(window_s=30.0)
    e.add(MIC, 0.0, tone(10.0, 800))  # mic covers 0..10
    # system track simply hasn't arrived yet — span could still be covered
    mic = [TimedSegment(2.0, 4.0, "wait for the system chunk")]
    out, deferred = attribute(mic, [], e, AttributionConfig())
    assert out == [] and deferred[MIC] == mic
