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


def test_dense_window_split_by_budget():
    """69-min soak (2026-08-25): a 20-min window overflowed the context and
    the model returned prose. Oversized windows must split by size."""
    calls = []

    def gen(prompt, system):
        calls.append(len(prompt))
        return GOOD if "NOTES:" in prompt else FINAL

    # one time-window, but far more text than a 300-token budget allows
    segs = [seg(i, float(i), "dense meeting speech with many words " * 8) for i in range(30)]
    summarize(segs, "s", gen, window_s=1200.0, budget_tokens=300)
    map_calls = calls[:-1]
    assert len(map_calls) > 1  # split happened
    assert all(c < 300 * 4 + 700 for c in map_calls)  # each fits budget + template


def test_reduce_renumbered_citation_is_retried():
    """5-h soak (2026-09-01): the reduce model renumbered citations, which
    'validated' against the global excerpt index while pointing at the wrong
    segment. A marker outside the call's input must trigger a retry."""
    reduce_calls = []

    def gen(prompt, system):
        if "NOTES:" in prompt:
            return GOOD  # cites [1], the only excerpt
        reduce_calls.append(prompt)
        if len(reduce_calls) == 1:
            return FINAL.replace("[1]", "[6]")  # invented marker
        return FINAL

    content = summarize([seg(7, 1.0, "a point was made")], "s", gen)
    assert len(reduce_calls) == 2
    assert "copy citation numbers exactly" in reduce_calls[1]
    assert content.key_points[0].citations[0].seq == 7  # real segment, not [6]


def test_reduce_persistent_invalid_markers_stripped_not_miscited():
    """If the retry still invents markers, the bullet loses its citation and
    is dropped — never stored pointing at the wrong transcript moment."""

    def gen(prompt, system):
        if "NOTES:" in prompt:
            return GOOD
        return FINAL.replace("[1]", "[6]")  # invalid both attempts

    content = summarize([seg(7, 1.0, "a point was made")], "s", gen)
    assert content.overview  # summary still completes
    assert content.key_points == []  # uncited bullet dropped, not miscited


def test_four_digit_markers_are_visible():
    """Global renumbering exceeds [999] on 5-hour transcripts; the old
    3-digit marker regex silently ignored those citations."""
    from ambient_recorder.assistant.summarize import _markers_in

    assert _markers_in("a point [1002], another [7]") == {1002, 7}


def test_all_none_window_is_valid_not_malformed():
    """69-min soak (2026-08-25): a trailing near-empty window correctly
    yields all-'none' sections; that is structure, not a malformed reply."""
    def gen(prompt, system):
        if "NOTES:" in prompt:
            return "KEY POINTS:\n- none\nDECISIONS:\n- none\nACTION ITEMS:\n- none"
        return FINAL

    content = summarize([seg(0, 1.0, "Hmm")], "s", gen)
    assert content.overview  # completed, no MalformedOutputError
