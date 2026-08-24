"""Lexical excerpt retrieval + prompt-budget packing (research R3). Pure."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ambient_recorder.models.transcript import TranscriptSegment

_WORD = re.compile(r"[a-z0-9']+")
_STOP = frozenset(
    "the a an and or but of to in on at for with about is are was were be been "
    "i you he she it we they this that what when who how did do does said say".split()
)
_CHARS_PER_TOKEN = 4  # budget approximation


@dataclass
class Excerpt:
    n: int  # citation number shown to the model
    session_id: str
    transcript_id: str
    seq: int
    start_s: float
    source: str  # me | them
    text: str

    def render(self) -> str:
        m, s = divmod(int(self.start_s), 60)
        h, m = divmod(m, 60)
        return f"[{self.n}] {h:02d}:{m:02d}:{s:02d} {self.source}: {self.text}"


def _terms(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in _STOP}


def select_excerpts(
    question: str,
    history: list[str],
    segments: list[TranscriptSegment],
    *,
    session_id: str,
    budget_tokens: int,
    live: bool,
) -> list[Excerpt]:
    """Score segments by term overlap with the question (+ light history
    weight), recency-biased when live; pack top scorers into the budget in
    chronological order with contiguous-neighbour inclusion."""
    if not segments:
        return []
    q_terms = _terms(question)
    h_terms = _terms(" ".join(history[-3:])) if history else set()
    max_seq = max(s.seq for s in segments)

    def score(s: TranscriptSegment) -> float:
        t = _terms(s.text)
        base = 2.0 * len(q_terms & t) + 0.5 * len(h_terms & t)
        if live and max_seq:
            base += 1.5 * (s.seq / max_seq)  # recent segments matter more live
        return base

    ranked = sorted(segments, key=score, reverse=True)
    chosen: dict[int, TranscriptSegment] = {}
    by_seq = {s.seq: s for s in segments}
    budget_chars = budget_tokens * _CHARS_PER_TOKEN
    used = 0
    for s in ranked:
        if score(s) <= 0 and chosen:
            break
        # include the segment and its immediate neighbours for local context
        for seq in (s.seq - 1, s.seq, s.seq + 1):
            n = by_seq.get(seq)
            if n is None or n.seq in chosen:
                continue
            cost = len(n.text) + 24
            if used + cost > budget_chars:
                continue
            chosen[n.seq] = n
            used += cost
        if used >= budget_chars * 0.95:
            break
    if not chosen:  # nothing scored: fall back to the most recent context
        for s in sorted(segments, key=lambda x: x.seq, reverse=True):
            cost = len(s.text) + 24
            if used + cost > budget_chars:
                break
            chosen[s.seq] = s
            used += cost
    ordered = sorted(chosen.values(), key=lambda s: s.seq)
    return [
        Excerpt(
            n=i + 1,
            session_id=session_id,
            transcript_id=s.transcript_id,
            seq=s.seq,
            start_s=s.start_s,
            source=s.source.value,
            text=s.text,
        )
        for i, s in enumerate(ordered)
    ]
