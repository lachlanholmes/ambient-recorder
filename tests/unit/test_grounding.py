"""T010: citation validation + verdicts."""

from __future__ import annotations

from ambient_recorder.assistant.grounding import (
    DECLINE_PHRASE,
    GroundingVerdict,
    validate_citations,
)
from ambient_recorder.assistant.retrieval import Excerpt


def ex(n: int, seq: int) -> Excerpt:
    return Excerpt(
        n=n,
        session_id="s",
        transcript_id="t",
        seq=seq,
        start_s=seq * 10.0,
        source="them",
        text=f"segment {seq}",
    )


EXCERPTS = [ex(1, 10), ex(2, 11), ex(3, 12)]


def test_valid_citations_extracted():
    text, cits, verdict = validate_citations("The date moved to Thursday [2][3].", EXCERPTS)
    assert verdict == GroundingVerdict.GROUNDED
    assert [c.seq for c in cits] == [11, 12]
    assert "[2]" in text and "[3]" in text


def test_invalid_marker_stripped():
    text, cits, verdict = validate_citations("Thursday [2], maybe [9].", EXCERPTS)
    assert verdict == GroundingVerdict.GROUNDED
    assert [c.seq for c in cits] == [11]
    assert "[9]" not in text


def test_zero_citations_is_ungrounded():
    text, cits, verdict = validate_citations("They agreed to ship it early.", EXCERPTS)
    assert verdict == GroundingVerdict.UNGROUNDED
    assert cits == []


def test_decline_phrase_detected():
    for answer in (
        DECLINE_PHRASE,
        DECLINE_PHRASE.capitalize() + ".",
        f"That was {DECLINE_PHRASE}.",
    ):
        _, cits, verdict = validate_citations(answer, EXCERPTS)
        assert verdict == GroundingVerdict.DECLINED, answer
        assert cits == []


def test_long_answer_containing_phrase_is_not_decline():
    long = (
        "The pricing was covered at length [1], though the office move was "
        f"{DECLINE_PHRASE}, they did decide the budget [2]."
    )
    _, cits, verdict = validate_citations(long, EXCERPTS)
    assert verdict == GroundingVerdict.GROUNDED
    assert len(cits) == 2
