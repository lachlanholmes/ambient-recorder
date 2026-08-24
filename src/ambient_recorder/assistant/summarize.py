"""Staged-condensation summary orchestration (research R4, T014).

Map: per-window structured bullets with citations. Reduce: merge; a
second tier activates when bullet volume exceeds the budget. Parsing is
line-oriented and forgiving, with one retry on malformed output.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from ambient_recorder.assistant.grounding import _MARKER  # citation marker regex
from ambient_recorder.assistant.prompts import (
    SUMMARY_MAP_SYSTEM,
    SUMMARY_REDUCE_SYSTEM,
    summary_map_prompt,
    summary_reduce_prompt,
)
from ambient_recorder.assistant.retrieval import Excerpt
from ambient_recorder.models.assistant import ActionItem, Citation, SummaryContent, SummaryItem
from ambient_recorder.models.transcript import Speaker, TranscriptSegment

# generate(prompt, system) -> full text (worker adapts the streaming engine)
GenerateFn = Callable[[str, str], str]

_SECTION = re.compile(r"^(OVERVIEW|KEY POINTS|DECISIONS|ACTION ITEMS):\s*$", re.I)
_BULLET = re.compile(r"^\s*[-*]\s+(.*)$")
_CHARS_PER_TOKEN = 4


def windows(
    segments: list[TranscriptSegment], window_s: float = 1200.0
) -> list[list[TranscriptSegment]]:
    out: list[list[TranscriptSegment]] = []
    cur: list[TranscriptSegment] = []
    edge = window_s
    for s in sorted(segments, key=lambda x: (x.start_s, x.seq)):
        if s.start_s >= edge and cur:
            out.append(cur)
            cur = []
            while s.start_s >= edge:
                edge += window_s
        cur.append(s)
    if cur:
        out.append(cur)
    return out


def _excerpts(segs: list[TranscriptSegment], session_id: str) -> list[Excerpt]:
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
        for i, s in enumerate(segs)
    ]


def _parse_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    overview_lines: list[str] = []
    for line in text.splitlines():
        m = _SECTION.match(line.strip())
        if m:
            current = m.group(1).upper()
            sections.setdefault(current, [])
            continue
        if line.strip().upper().startswith("OVERVIEW:"):
            current = "OVERVIEW"
            rest = line.split(":", 1)[1].strip()
            if rest:
                overview_lines.append(rest)
            sections.setdefault(current, [])
            continue
        if current == "OVERVIEW" and line.strip() and not _BULLET.match(line):
            overview_lines.append(line.strip())
            continue
        b = _BULLET.match(line)
        if b and current:
            item = b.group(1).strip()
            if item.lower() != "none":
                sections[current].append(item)
    if overview_lines:
        sections["OVERVIEW"] = [" ".join(overview_lines)]
    return sections


def _bullet_citations(text: str, by_n: dict[int, Excerpt]) -> tuple[str, list[Citation]]:
    cits: list[Citation] = []
    seen: set[int] = set()

    def _sub(m: re.Match) -> str:
        n = int(m.group(1))
        e = by_n.get(n)
        if e is None:
            return ""
        if n not in seen:
            seen.add(n)
            cits.append(
                Citation(
                    session_id=e.session_id,
                    transcript_id=e.transcript_id,
                    seq=e.seq,
                    start_s=e.start_s,
                )
            )
        return m.group(0)

    _MARKER.sub(_sub, text)  # collect citations
    # Summary citations live in the structured list; markers are stripped
    # from stored text entirely (unlike Q&A answers, where inline [n]
    # markers are the display convention).
    cleaned = re.sub(r"\s+", " ", _MARKER.sub("", text)).strip()
    return cleaned, cits


def _parse_action(text: str) -> tuple[Speaker, str, str | None] | None:
    parts = [p.strip() for p in text.split("|")]
    if len(parts) < 2:
        return None
    owner_raw = parts[0].lower().strip("() ")
    owner = (
        Speaker.ME
        if "me" in owner_raw.split() or owner_raw == "me"
        else (Speaker.THEM if "them" in owner_raw else None)
    )
    if owner is None:
        return None
    task = parts[1]
    deadline = parts[2] if len(parts) > 2 and parts[2] not in ("-", "") else None
    return owner, task, deadline


class MalformedOutputError(Exception):
    pass


def summarize(
    segments: list[TranscriptSegment],
    session_id: str,
    generate: GenerateFn,
    *,
    window_s: float = 1200.0,
    budget_tokens: int = 3000,
) -> SummaryContent:
    """Full pipeline. `generate` is called once per window + once per reduce
    tier; each call gets one retry on malformed structure."""
    win = windows(segments, window_s)
    notes: list[str] = []
    excerpt_index: dict[int, Excerpt] = {}
    offset = 0
    for w in win:
        ex = _excerpts(w, session_id)
        # renumber globally so citations survive the reduce
        for e in ex:
            e.n += offset
            excerpt_index[e.n] = e
        offset += len(ex)
        notes.append(
            _call_checked(
                generate, summary_map_prompt(ex), SUMMARY_MAP_SYSTEM, require_overview=False
            )
        )

    # second reduce tier if the notes themselves blow the budget
    budget_chars = budget_tokens * _CHARS_PER_TOKEN
    while len(notes) > 1 and sum(len(n) for n in notes) > budget_chars:
        merged: list[str] = []
        group: list[str] = []
        size = 0
        for n in notes:
            if group and size + len(n) > budget_chars:
                merged.append(
                    _call_checked(
                        generate,
                        summary_reduce_prompt(group),
                        SUMMARY_REDUCE_SYSTEM,
                        require_overview=False,
                    )
                )
                group, size = [], 0
            group.append(n)
            size += len(n)
        if group:
            merged.append(
                _call_checked(
                    generate,
                    summary_reduce_prompt(group),
                    SUMMARY_REDUCE_SYSTEM,
                    require_overview=False,
                )
            )
        if len(merged) >= len(notes):  # no progress; bail to a single reduce
            notes = merged
            break
        notes = merged

    # Always run the final reduce — even one window's notes need the
    # OVERVIEW-bearing final structure.
    final_text = _call_checked(
        generate, summary_reduce_prompt(notes), SUMMARY_REDUCE_SYSTEM, require_overview=True
    )
    sections = _parse_sections(final_text)

    def items(section: str) -> list[SummaryItem]:
        out = []
        for b in sections.get(section, []):
            text, cits = _bullet_citations(b, excerpt_index)
            if text and cits:
                out.append(SummaryItem(text=text, citations=cits))
        return out

    actions: list[ActionItem] = []
    for b in sections.get("ACTION ITEMS", []):
        text, cits = _bullet_citations(b, excerpt_index)
        parsed = _parse_action(text)
        if parsed and cits:
            owner, task, deadline = parsed
            actions.append(
                ActionItem(text=task, owner=owner, deadline_text=deadline, citations=cits)
            )
    overview = " ".join(sections.get("OVERVIEW", [])) or "No overview produced."
    return SummaryContent(
        overview=overview,
        key_points=items("KEY POINTS"),
        decisions=items("DECISIONS"),
        action_items=actions,
    )


def _call_checked(generate: GenerateFn, prompt: str, system: str, *, require_overview: bool) -> str:
    """One retry if the output has no recognisable structure (R4)."""
    for attempt in (1, 2):
        text = generate(prompt, system)
        sections = _parse_sections(text)
        has_bullets = any(v for k, v in sections.items() if k != "OVERVIEW")
        has_overview = bool(sections.get("OVERVIEW"))
        if has_bullets or (require_overview and has_overview):
            return text
        if attempt == 1:
            prompt = (
                prompt
                + "\n\nIMPORTANT: use exactly the required section headings and dash bullets."
            )
    raise MalformedOutputError("model output had no parseable structure after retry")
