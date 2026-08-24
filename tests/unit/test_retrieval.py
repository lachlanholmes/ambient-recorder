"""T009: lexical retrieval + budget packing."""

from __future__ import annotations

from ambient_recorder.assistant.retrieval import select_excerpts
from ambient_recorder.models.transcript import Speaker, TranscriptSegment


def seg(seq: int, text: str, source=Speaker.THEM) -> TranscriptSegment:
    return TranscriptSegment(
        transcript_id="t",
        seq=seq,
        source=source,
        start_s=seq * 10.0,
        end_s=seq * 10.0 + 5,
        text=text,
    )


SEGS = [
    seg(0, "good morning everyone welcome"),
    seg(1, "the certificate problem pushed the mobile release by a week"),
    seg(2, "customer feedback on the dashboard has been positive", Speaker.ME),
    seg(3, "we need the pricing decision before the end of the month"),
    seg(4, "thursday the fourteenth pending QA sign off"),
]


def test_relevant_segment_ranks_first():
    ex = select_excerpts(
        "what about the certificate problem?",
        [],
        SEGS,
        session_id="s",
        budget_tokens=200,
        live=False,
    )
    texts = [e.text for e in ex]
    assert any("certificate" in t for t in texts)
    # neighbours included for context
    assert any("welcome" in t or "dashboard" in t for t in texts)


def test_budget_respected():
    big = [seg(i, f"filler words about topic {i} " * 20) for i in range(50)]
    ex = select_excerpts("topic 25", [], big, session_id="s", budget_tokens=300, live=False)
    assert sum(len(e.text) for e in ex) <= 300 * 4 + 100


def test_live_recency_bias():
    dup = [seg(0, "the budget number is four"), seg(40, "the budget number is nine")]
    ex_live = select_excerpts(
        "what is the budget number?", [], dup, session_id="s", budget_tokens=60, live=True
    )
    assert ex_live[-1].seq == 40  # recent one wins under tight budget


def test_numbering_is_chronological_and_stable():
    ex = select_excerpts(
        "pricing decision", [], SEGS, session_id="s", budget_tokens=500, live=False
    )
    assert [e.n for e in ex] == list(range(1, len(ex) + 1))
    assert [e.seq for e in ex] == sorted(e.seq for e in ex)


def test_no_match_falls_back_to_recent():
    ex = select_excerpts("zzz qqq xyzzy", [], SEGS, session_id="s", budget_tokens=500, live=False)
    assert ex, "fallback must return context"
