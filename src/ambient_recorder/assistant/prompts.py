"""Prompt templates (research R3/R4). Pure string assembly; golden-tested."""

from __future__ import annotations

from ambient_recorder.assistant.grounding import DECLINE_PHRASE
from ambient_recorder.assistant.retrieval import Excerpt

QA_SYSTEM = (
    "You are a meeting assistant. Answer questions using ONLY the numbered "
    "meeting excerpts provided. 'me' is the user; 'them' is the other "
    "participants. After every claim, cite the excerpt number in square "
    f"brackets, like [3]. If the excerpts do not contain the answer, reply "
    f'exactly: "{DECLINE_PHRASE}". Never invent content.'
)

SUMMARY_MAP_SYSTEM = (
    "You extract structured notes from meeting transcript excerpts. "
    "'me' is the user; 'them' is the other participants. Use ONLY the "
    "excerpts. Cite excerpt numbers like [3] after every bullet. "
    "Output exactly these sections, each a dash-bullet list (write 'none' "
    "if empty):\nKEY POINTS:\nDECISIONS:\nACTION ITEMS:\n"
    "For action items use: owner (me|them) | task | deadline (verbatim "
    "spoken words, or '-'). Anything someone commits to DOING is an action "
    "item, not a decision — e.g. spoken 'I will draft options by Friday' "
    "becomes: - me | draft options | by Friday [7]"
)

SUMMARY_REDUCE_SYSTEM = (
    "You merge meeting notes into a final summary. Deduplicate, keep "
    "citations like [3] intact, keep owners and verbatim deadlines. "
    "Output exactly these sections:\nOVERVIEW: (2-4 sentences)\n"
    "KEY POINTS:\nDECISIONS:\nACTION ITEMS:\n"
    "Bullets as dashes; action items as: owner (me|them) | task | deadline "
    "(e.g. - me | draft options | by Friday [7]). Commitments to do "
    "something are action items, never decisions."
)


def render_excerpts(excerpts: list[Excerpt]) -> str:
    return "\n".join(e.render() for e in excerpts)


def qa_prompt(excerpts: list[Excerpt], history: list[tuple[str, str]], question: str) -> str:
    parts = ["MEETING EXCERPTS:", render_excerpts(excerpts), ""]
    if history:
        parts.append("CONVERSATION SO FAR:")
        for q, a in history[-4:]:
            parts += [f"Q: {q}", f"A: {a}"]
        parts.append("")
    parts += [f"QUESTION: {question}", "ANSWER:"]
    return "\n".join(parts)


def summary_map_prompt(excerpts: list[Excerpt]) -> str:
    return f"TRANSCRIPT EXCERPTS:\n{render_excerpts(excerpts)}\n\nNOTES:"


def summary_reduce_prompt(window_notes: list[str]) -> str:
    joined = "\n\n---\n\n".join(window_notes)
    return f"NOTES FROM MEETING SECTIONS (chronological):\n{joined}\n\nFINAL SUMMARY:"
