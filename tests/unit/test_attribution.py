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


def test_identical_words_collapse_to_one_copy():
    """2026-08-27 rule: identical words at identical times are one utterance.
    Even with the mic clearly louder (user echoing what was played), the
    transcript keeps a single copy — the system one, since loopback cannot
    contain mic bleed."""
    e = _buf(mic_amp=6400, sys_amp=800)
    mic = [TimedSegment(1.0, 3.0, "sounds good to me")]
    sys = [TimedSegment(1.0, 3.0, "sounds good to me")]
    out, _ = attribute(mic, sys, e, AttributionConfig())
    assert [s.source.value for s in out] == ["them"]


def test_fused_bleed_prefix_trimmed_keeps_genuine_remainder():
    """Field 2026-08-27: Whisper fused a bleed sentence with the user's
    genuine reply into one loud mic segment. The bleed prefix is trimmed;
    the genuine remainder survives as `me`."""
    e = _buf(mic_amp=6400, sys_amp=800)
    mic = [
        TimedSegment(
            0.5, 6.0, "Good morning, shall we start with the roadmap? Yes, let's begin now"
        )
    ]
    sys = [TimedSegment(0.0, 3.4, "Good morning, shall we start with the roadmap?")]
    out, _ = attribute(mic, sys, e, AttributionConfig())
    by_src = {s.source.value: s.text for s in out}
    assert by_src["them"].startswith("Good morning")
    assert "begin now" in by_src["me"] and "roadmap" not in by_src["me"]


def test_overlap_talk_both_kept_when_words_differ():
    e = _buf(mic_amp=800, sys_amp=6400)
    mic = [TimedSegment(1.0, 3.0, "wait I disagree")]
    sys = [TimedSegment(1.0, 3.0, "and the budget is approved")]
    out, _ = attribute(mic, sys, e, AttributionConfig())
    assert sorted(s.source.value for s in out) == ["me", "them"]


def test_ambiguous_gap_with_twin_drops_bleed():
    """THE 2026-08-27 regression case: mic AGC closed the bleed gap to
    ~5 dB (under the old 6 dB cliff) and duplicates sailed through. With a
    twin, any gap short of clearly-mic-louder is bleed."""
    e = _buf(mic_amp=1000, sys_amp=1900)  # system +5.6 dB — ambiguous zone
    mic = [TimedSegment(1.0, 3.0, "same words here")]
    sys = [TimedSegment(1.0, 3.0, "same words here")]
    out, _ = attribute(mic, sys, e, AttributionConfig())
    assert [s.source.value for s in out] == ["them"]


def test_overlapping_but_different_words_kept_regardless_of_gap():
    e = _buf(mic_amp=1000, sys_amp=1900)  # ambiguous gap, but no twin
    mic = [TimedSegment(1.0, 3.0, "wait I have a question")]
    sys = [TimedSegment(1.0, 3.0, "and the budget is approved")]
    out, _ = attribute(mic, sys, e, AttributionConfig())
    assert sorted(s.source.value for s in out) == ["me", "them"]


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


def test_expired_mic_with_system_twin_is_dropped_once():
    """Regression 2026-08-27: the T038 rerun with 003's prewarm contention
    produced 6/6 bleed duplicates — expired mic copies emitted despite the
    system track having transcribed the same words. Expired + twin → drop."""
    e = EnergyBuffer(window_s=30.0)
    e.add(MIC, 0.0, tone(40.0, 800))
    e.add(SYS, 35.0, tone(5.0, 8000))  # window slid past 2..4 on system
    mic = [TimedSegment(2.0, 4.0, "good morning shall we start with the roadmap")]
    sys = [TimedSegment(2.1, 4.1, "Good morning, shall we start with the roadmap?")]
    out, deferred = attribute(
        mic, sys, e, AttributionConfig(), transcribed_until={MIC: 40.0, SYS: 40.0}
    )
    assert [s.source.value for s in out] == ["them"]  # exactly one copy survives
    assert not deferred[MIC]


def test_expired_system_never_twin_dropped():
    """Asymmetry guard: if both tracks expired, only the mic side drops on
    a twin — otherwise both copies could vanish."""
    e = EnergyBuffer(window_s=30.0)
    e.add(MIC, 100.0, tone(5.0, 800))  # both windows start far past the span
    e.add(SYS, 100.0, tone(5.0, 8000))
    mic = [TimedSegment(2.0, 4.0, "identical words here")]
    sys = [TimedSegment(2.0, 4.0, "identical words here")]
    out, _ = attribute(mic, sys, e, AttributionConfig(), transcribed_until={MIC: 105.0, SYS: 105.0})
    assert "them" in [s.source.value for s in out]  # system copy always survives


def test_fused_bleed_suffix_trimmed():
    """Field 2026-08-27 residual: bleed fused at the segment END ('I saw
    that. Do we have a new date? Thursday the 14th pending QA sign-o')."""
    e = _buf(mic_amp=6400, sys_amp=800)
    mic = [
        TimedSegment(
            1.0, 8.0, "I saw that. Do we have a new date? Thursday the 14th pending QA sign o"
        )
    ]
    sys = [TimedSegment(4.0, 7.5, "Thursday the 14th, pending QA sign-off.")]
    out, _ = attribute(mic, sys, e, AttributionConfig())
    by_src = {s.source.value: s.text for s in out}
    assert "new date" in by_src["me"] and "Thursday" not in by_src["me"]
    assert "Thursday" in by_src["them"]
