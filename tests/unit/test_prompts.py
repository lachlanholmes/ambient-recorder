"""T011: prompt templates — golden structure, not exact text."""

from __future__ import annotations

from ambient_recorder.assistant.grounding import DECLINE_PHRASE
from ambient_recorder.assistant.prompts import (
    QA_SYSTEM,
    qa_prompt,
    summary_map_prompt,
    summary_reduce_prompt,
)
from ambient_recorder.assistant.retrieval import Excerpt

EX = [
    Excerpt(
        n=1,
        session_id="s",
        transcript_id="t",
        seq=10,
        start_s=724.0,
        source="them",
        text="ship on thursday",
    )
]


def test_qa_system_contains_the_contract():
    assert DECLINE_PHRASE in QA_SYSTEM
    assert "[3]" in QA_SYSTEM  # cite-by-number instruction


def test_qa_prompt_structure():
    p = qa_prompt(EX, [("earlier q", "earlier a")], "when do we ship?")
    assert "[1] 00:12:04 them: ship on thursday" in p
    assert p.index("MEETING EXCERPTS:") < p.index("CONVERSATION SO FAR:") < p.index("QUESTION:")
    assert p.rstrip().endswith("ANSWER:")


def test_qa_prompt_without_history():
    p = qa_prompt(EX, [], "when?")
    assert "CONVERSATION SO FAR" not in p


def test_summary_prompts():
    assert "NOTES:" in summary_map_prompt(EX)
    r = summary_reduce_prompt(["notes a", "notes b"])
    assert "notes a" in r and "---" in r and r.rstrip().endswith("FINAL SUMMARY:")
