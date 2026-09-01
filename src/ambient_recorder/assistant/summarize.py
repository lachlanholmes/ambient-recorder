"""Staged-condensation summary orchestration (research R4, T014).

Map: per-window structured bullets with citations. Reduce: merge; a
second tier activates when bullet volume exceeds the budget. Parsing is
line-oriented and forgiving, with one retry on malformed output.
"""

from __future__ import annotations

import difflib
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
    # Dense meetings can pack more text into a time window than the prompt
    # budget allows (found live 2026-08-25 on the 69-min soak): re-split any
    # oversized window by size so every map prompt fits the context.
    budget_chars_map = budget_tokens * _CHARS_PER_TOKEN
    sized: list[list[TranscriptSegment]] = []
    for w in win:
        cur: list[TranscriptSegment] = []
        size = 0
        for s in w:
            cost = len(s.text) + 24
            if cur and size + cost > budget_chars_map:
                sized.append(cur)
                cur, size = [], 0
            cur.append(s)
            size += cost
        if cur:
            sized.append(cur)
    win = sized
    notes: list[str] = []
    excerpt_index: dict[int, Excerpt] = {}
    offset = 0
    source_bullets: list[tuple[str, list[Citation]]] = []
    for w in win:
        # Excerpts are presented to the model with LOCAL numbers (1..N):
        # the 5-h repro (2026-09-01) showed the model cannot reliably cite
        # globally renumbered excerpts — windows numbered 1189.. got small
        # invented markers or none at all, while windows numbered from 1
        # cited correctly. Markers are translated to global numbers in code
        # after validation, so uniqueness across windows never depends on
        # the model.
        ex = _excerpts(w, session_id)
        note = _call_checked(
            generate,
            summary_map_prompt(ex),
            SUMMARY_MAP_SYSTEM,
            require_overview=False,
            allowed_markers={e.n for e in ex},
            require_citations=True,
        )
        note = _MARKER.sub(lambda m, off=offset: f"[{int(m.group(1)) + off}]", note)
        for e in ex:
            e.n += offset
            excerpt_index[e.n] = e
        offset += len(ex)
        notes.append(note)
        for sec_bullets in _parse_sections(note).values():
            for b in sec_bullets:
                text, cits = _bullet_citations(b, excerpt_index)
                if text and cits:
                    source_bullets.append((text.lower(), cits))

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
                        allowed_markers=set().union(*(_markers_in(g) for g in group)),
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
                    allowed_markers=set().union(*(_markers_in(g) for g in group)),
                )
            )
        if len(merged) >= len(notes):  # no progress; bail to a single reduce
            notes = merged
            break
        notes = merged

    # Always run the final reduce — even one window's notes need the
    # OVERVIEW-bearing final structure.
    final_text = _call_checked(
        generate,
        summary_reduce_prompt(notes),
        SUMMARY_REDUCE_SYSTEM,
        require_overview=True,
        allowed_markers=set().union(set(), *(_markers_in(n) for n in notes)),
    )
    sections = _parse_sections(final_text)

    def _inherit(text: str, cits: list[Citation]) -> list[Citation]:
        # A final bullet the model failed to cite inherits citations from
        # the best-matching map-stage bullet (which carries verified global
        # markers). Deterministic — the reduce model copying numbers is a
        # bonus, not a requirement.
        if cits or not source_bullets:
            return cits
        key = text.lower()
        best_ratio, best_cits = 0.0, []
        for src_text, src_cits in source_bullets:
            r = difflib.SequenceMatcher(None, key, src_text).ratio()
            if r > best_ratio:
                best_ratio, best_cits = r, src_cits
        return best_cits if best_ratio >= 0.55 else []

    def items(section: str) -> list[SummaryItem]:
        out = []
        for b in sections.get(section, []):
            text, cits = _bullet_citations(b, excerpt_index)
            cits = _inherit(text, cits)
            if text and cits:
                out.append(SummaryItem(text=text, citations=cits))
        return out

    actions: list[ActionItem] = []
    for b in sections.get("ACTION ITEMS", []):
        text, cits = _bullet_citations(b, excerpt_index)
        cits = _inherit(text, cits)
        parsed = _parse_action(text)
        if parsed and cits:
            owner, task, deadline = parsed
            actions.append(
                ActionItem(text=task, owner=owner, deadline_text=deadline, citations=cits)
            )
    raw_overview = " ".join(sections.get("OVERVIEW", []))
    overview = re.sub(r"\s+", " ", _MARKER.sub("", raw_overview)).strip() or "No overview produced."
    return SummaryContent(
        overview=overview,
        key_points=items("KEY POINTS"),
        decisions=items("DECISIONS"),
        action_items=actions,
    )


def _markers_in(text: str) -> set[int]:
    return {int(m.group(1)) for m in _MARKER.finditer(text)}


def _strip_markers(text: str, invalid: set[int]) -> str:
    return _MARKER.sub(lambda m: "" if int(m.group(1)) in invalid else m.group(0), text)


def _call_checked(
    generate: GenerateFn,
    prompt: str,
    system: str,
    *,
    require_overview: bool,
    allowed_markers: set[int] | None = None,
    require_citations: bool = False,
) -> str:
    """One retry if the output has no recognisable structure (R4), or if it
    cites markers that were not in its input. The latter guards the reduce
    tiers: the 5-h soak (2026-09-01) showed the merge model renumbering
    citations, which then 'validated' against the global excerpt index while
    pointing at the wrong segment. If the retry still invents markers, the
    invalid ones are stripped — downstream drops uncited bullets, which is
    honest; a wrong citation is not."""
    fallback: str | None = None
    for attempt in (1, 2):
        text = generate(prompt, system)
        sections = _parse_sections(text)
        # Structure = the section HEADINGS were produced. An all-'none'
        # window (e.g. a trailing "me: Hmm") is a valid empty result, not
        # malformed — found live 2026-08-25 on the 69-min soak.
        has_sections = any(k != "OVERVIEW" for k in sections)
        has_overview = bool(sections.get("OVERVIEW"))
        structured = has_sections or (require_overview and has_overview)
        markers = _markers_in(text)
        invalid = markers - allowed_markers if allowed_markers is not None else set()
        # 5-h repro (2026-09-01): the commonest map failure is bullets with
        # NO citations at all — those die downstream, so an entirely
        # uncited-but-bulleted reply earns the retry too.
        has_bullets = any(v for k, v in sections.items() if k != "OVERVIEW")
        uncited = require_citations and has_bullets and not markers
        if structured and not invalid and not uncited:
            return text
        if structured:
            fallback = _strip_markers(text, invalid)
        if attempt == 1:
            if not structured:
                prompt = (
                    prompt
                    + "\n\nIMPORTANT: use exactly the required section headings and dash bullets."
                )
            elif uncited:
                prompt = (
                    prompt
                    + "\n\nIMPORTANT: every bullet must end with the number of the excerpt "
                    + "that supports it, like [12]."
                )
            else:
                prompt = (
                    prompt
                    + "\n\nIMPORTANT: copy citation numbers exactly as they appear in the "
                    + "input above; do not renumber and do not invent citations."
                )
    if fallback is not None:
        return fallback
    raise MalformedOutputError("model output had no parseable structure after retry")
