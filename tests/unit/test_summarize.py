"""T014: windowing, parse-retry, second reduce tier (fake generate fns)."""

from __future__ import annotations

import pytest

from ambient_recorder.assistant.summarize import (
    MalformedOutputError,
    _parse_sections,
    summarize,
    windows,
)
from ambient_recorder.models.transcript import Speaker, TranscriptSegment


def seg(seq: int, start_s: float, text="words") -> TranscriptSegment:
    return TranscriptSegment(
        transcript_id="t",
        seq=seq,
        source=Speaker.THEM,
        start_s=start_s,
        end_s=start_s + 5,
        text=text,
    )


def test_windows_split_on_time():
    segs = [seg(i, i * 300.0) for i in range(10)]  # 0..2700 s
    w = windows(segs, window_s=1200.0)
    assert [len(x) for x in w] == [4, 4, 2]
    assert w[1][0].start_s == 1200.0


def test_windows_empty_and_single():
    assert windows([]) == []
    assert [len(x) for x in windows([seg(0, 5.0)])] == [1]


GOOD = "KEY POINTS:\n- a point [1]\nDECISIONS:\n- none\nACTION ITEMS:\n- none"
FINAL = "OVERVIEW: Fine.\nKEY POINTS:\n- a point [1]\nDECISIONS:\n- none\nACTION ITEMS:\n- none"


def test_parse_retry_recovers_from_one_malformed():
    calls = []

    def gen(prompt, system):
        calls.append(prompt)
        if len(calls) == 1:
            return "sorry, here is prose with no structure at all"
        return GOOD if "NOTES:" in prompt else FINAL

    content = summarize([seg(0, 1.0, "a point was made")], "s", gen)
    assert content.key_points and content.key_points[0].text == "a point"
    assert "IMPORTANT" in calls[1]  # retry carried the nudge


def test_persistent_malformed_raises():
    def gen(prompt, system):
        return "still just prose"

    with pytest.raises(MalformedOutputError):
        summarize([seg(0, 1.0)], "s", gen)


def test_second_reduce_tier_activates():
    reduce_calls = []

    def gen(prompt, system):
        if "NOTES:" in prompt:
            return GOOD.replace("a point", "p" * 900)  # bulky notes
        reduce_calls.append(prompt)
        return FINAL

    segs = [seg(i, i * 1200.0, "spread across many windows") for i in range(8)]
    summarize(segs, "s", gen, budget_tokens=300)  # tiny budget forces tiering
    assert len(reduce_calls) > 1  # intermediate reduces + final


def test_parse_sections_tolerates_inline_overview():
    s = _parse_sections("OVERVIEW: One line.\nKEY POINTS:\n- x [1]")
    assert s["OVERVIEW"] == ["One line."] and s["KEY POINTS"] == ["- x [1]".lstrip("- ")]
