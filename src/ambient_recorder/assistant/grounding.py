"""Citation extraction/validation + grounding verdict (research R3). Pure."""

from __future__ import annotations

import re
from enum import StrEnum

from ambient_recorder.assistant.retrieval import Excerpt
from ambient_recorder.models.assistant import Citation

DECLINE_PHRASE = "not discussed in this meeting"
# 4 digits: summaries renumber excerpts globally, and a 5-hour transcript
# exceeds [999] (found 2026-09-01 — 3-digit cap made big markers invisible
# to both citation collection and the reduce subset check).
_MARKER = re.compile(r"\[(\d{1,4})\]")


class GroundingVerdict(StrEnum):
    GROUNDED = "grounded"
    DECLINED = "declined"
    UNGROUNDED = "ungrounded"


def validate_citations(
    answer: str, excerpts: list[Excerpt]
) -> tuple[str, list[Citation], GroundingVerdict]:
    """Extract [n] markers, map valid ones to citations, strip invalid
    markers from the text. Verdict:
    - declined: the answer is (essentially) the decline phrase
    - grounded: at least one valid citation
    - ungrounded: substantive text, zero valid citations
    """
    by_n = {e.n: e for e in excerpts}
    seen: dict[int, Citation] = {}

    def _sub(m: re.Match) -> str:
        n = int(m.group(1))
        e = by_n.get(n)
        if e is None:
            return ""  # invalid marker: strip
        if n not in seen:
            seen[n] = Citation(
                session_id=e.session_id,
                transcript_id=e.transcript_id,
                seq=e.seq,
                start_s=e.start_s,
            )
        return m.group(0)

    cleaned = _MARKER.sub(_sub, answer).strip()
    cleaned = re.sub(r"  +", " ", cleaned)

    bare = _MARKER.sub("", cleaned).strip().strip(".").lower()
    if bare == DECLINE_PHRASE or (DECLINE_PHRASE in bare and len(bare) <= len(DECLINE_PHRASE) + 30):
        return cleaned, [], GroundingVerdict.DECLINED
    citations = [seen[n] for n in sorted(seen)]
    if citations:
        return cleaned, citations, GroundingVerdict.GROUNDED
    return cleaned, [], GroundingVerdict.UNGROUNDED
