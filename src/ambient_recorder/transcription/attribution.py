"""EnergyBuffer + two-track attribution with the bleed rule (research R4,
analyze U2). Pure logic — no I/O, no model."""

from __future__ import annotations

import math
import re
from collections import deque
from dataclasses import dataclass, field

import numpy as np

from ambient_recorder.models.session import PERSISTED_SAMPLE_RATE, SourceKind
from ambient_recorder.models.transcript import Speaker

_RES_S = 0.1  # 100 ms energy resolution
_WORD = re.compile(r"[a-z0-9']+")


@dataclass
class AttributionConfig:
    bleed_db: float = 6.0  # paired track louder by ≥ this → strong bleed suspicion
    # Mic clearly louder than system by MORE than this → genuine speech even
    # when the words match (2026-08-27 regression: mic AGC closed the bleed
    # gap to 5.2 dB, under bleed_db, and duplicates sailed through — with a
    # strong text twin, matching words are near-proof by themselves, so
    # energy only decides the clearly-mic-louder direction).
    mic_louder_db: float = 3.0
    overlap_ratio: float = 0.6  # ≥ this token overlap with a paired segment → same words
    energy_window_s: float = 300.0  # must exceed worst-case STT backlog (regression 2026-08-27)


@dataclass
class TimedSegment:
    start_s: float
    end_s: float
    text: str


@dataclass
class AttributedSegment:
    source: Speaker
    start_s: float
    end_s: float
    text: str


@dataclass
class _Track:
    origin_s: float | None = None  # session time of the oldest slot
    slots: deque = field(default_factory=deque)


class EnergyBuffer:
    """Per-track RMS (dBFS) at 100 ms resolution over a rolling window."""

    def __init__(self, window_s: float = 300.0):
        self._max_slots = int(window_s / _RES_S)
        self._tracks: dict[SourceKind, _Track] = {k: _Track() for k in SourceKind}

    def add(self, track: SourceKind, start_s: float, pcm16k_mono: bytes) -> None:
        t = self._tracks[track]
        samples = np.frombuffer(pcm16k_mono, dtype=np.int16).astype(np.float32) / 32768.0
        per_slot = int(PERSISTED_SAMPLE_RATE * _RES_S)
        n_slots = len(samples) // per_slot
        if t.origin_s is None:
            t.origin_s = start_s
        # Fill any gap between the last slot and this chunk's start with None.
        expected_start = t.origin_s + len(t.slots) * _RES_S
        gap = int(round((start_s - expected_start) / _RES_S))
        for _ in range(max(0, gap)):
            t.slots.append(None)
        for i in range(n_slots):
            block = samples[i * per_slot : (i + 1) * per_slot]
            rms = float(np.sqrt(np.mean(block * block))) if len(block) else 0.0
            t.slots.append(20 * math.log10(rms) if rms > 1e-6 else -120.0)
        while len(t.slots) > self._max_slots:
            t.slots.popleft()
            t.origin_s += _RES_S

    def rms_db(self, track: SourceKind, start_s: float, end_s: float) -> float | None:
        t = self._tracks[track]
        if t.origin_s is None:
            return None
        i0 = int(math.floor((start_s - t.origin_s) / _RES_S))
        i1 = int(math.ceil((end_s - t.origin_s) / _RES_S))
        if i0 < 0 or i1 > len(t.slots) or i1 <= i0:
            return None
        vals = [t.slots[i] for i in range(i0, i1)]
        if any(v is None for v in vals):
            return None
        # average in the linear power domain
        return 10 * math.log10(sum(10 ** (v / 10) for v in vals) / len(vals))

    def covered_until(self, track: SourceKind) -> float | None:
        t = self._tracks[track]
        return None if t.origin_s is None else t.origin_s + len(t.slots) * _RES_S

    def covers_start(self, track: SourceKind, start_s: float) -> bool:
        """True if the window still reaches back to `start_s` (i.e. a span
        starting there could still become fully covered)."""
        t = self._tracks[track]
        return t.origin_s is not None and t.origin_s <= start_s


def _tokens(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def _overlap_ratio(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def _time_overlap(a: TimedSegment, b: TimedSegment) -> bool:
    return a.start_s < b.end_s and b.start_s < a.end_s


def _trim_twin_edge(cand_text: str, twin_text: str, ratio: float) -> str | None:
    """Whisper sometimes FUSES a bleed sentence with the user's genuine
    speech into one mic segment, at either edge (field 2026-08-27: prefix
    'Good morning, shall we start…? Yes, let's begin' and suffix 'I saw
    that. Do we have a new date? Thursday the 14th pending QA sign-o').
    If either edge's words match the twin, return the genuine remainder;
    '' if nothing remains; None if the twin is not concentrated at an edge."""
    words = cand_text.split()
    twin_tokens = _tokens(twin_text)
    if not twin_tokens or not words:
        return None
    k = min(len(words), max(len(twin_tokens), 1))

    def edge_ratio(chunk: list[str]) -> float:
        toks = _tokens(" ".join(chunk))
        return len(toks & twin_tokens) / len(toks) if toks else 0.0

    if edge_ratio(words[:k]) >= ratio:  # bleed at the start
        remainder = " ".join(words[k:]).strip()
    elif edge_ratio(words[-k:]) >= ratio:  # bleed at the end
        remainder = " ".join(words[:-k]).strip()
    else:
        return None
    return remainder if len(_tokens(remainder)) >= 2 else ""


def find_twin(c: TimedSegment, others: list[TimedSegment], ratio: float) -> str | None:
    """Best same-words match for `c` among time-overlapping (±1 s) paired
    segments. Checked per-segment AND merged: per-segment because merging
    two unrelated sentences dilutes the ratio below threshold (field
    2026-08-27, replay 3 — a fused candidate scored exactly 0.5 against the
    merge of its twin plus an unrelated line); merged because one candidate
    can span words that the paired track split across two segments."""
    nearby = [o for o in others if o.start_s < c.end_s + 1.0 and o.end_s > c.start_s - 1.0]
    if not nearby:
        return None
    best = max(nearby, key=lambda o: _overlap_ratio(c.text, o.text))
    if _overlap_ratio(c.text, best.text) >= ratio:
        return best.text
    merged = " ".join(o.text for o in nearby)
    if _overlap_ratio(c.text, merged) >= ratio:
        return merged
    return None


def attribute(
    mic: list[TimedSegment],
    system: list[TimedSegment],
    energy: EnergyBuffer,
    cfg: AttributionConfig,
    transcribed_until: dict[SourceKind, float] | None = None,
) -> tuple[list[AttributedSegment], dict[SourceKind, list[TimedSegment]]]:
    """Returns (attributed, deferred). Deferred candidates lacked paired-track
    coverage (energy, or — when the other track is much louder — transcribed
    text) and must be resubmitted with the next chunk. `transcribed_until`
    gives, per track, the session time up to which that track's audio has
    been transcribed (None = unknown → never defer on text coverage)."""
    out: list[AttributedSegment] = []
    deferred: dict[SourceKind, list[TimedSegment]] = {SourceKind.MIC: [], SourceKind.SYSTEM: []}
    tu = transcribed_until or {}

    def decide(own: SourceKind, cands: list[TimedSegment], others: list[TimedSegment]) -> None:
        other = SourceKind.SYSTEM if own == SourceKind.MIC else SourceKind.MIC
        speaker = Speaker.ME if own == SourceKind.MIC else Speaker.THEM
        for c in cands:
            own_db = energy.rms_db(own, c.start_s, c.end_s)
            other_db = energy.rms_db(other, c.start_s, c.end_s)
            if own_db is None or other_db is None:
                # Coverage may be pending (paired chunk not arrived) or
                # EXPIRED (the rolling window slid past the span — found
                # live 2026-08-24: candidates deferred during a slow start
                # became permanently unjudgeable and lag grew unboundedly).
                expired = any(
                    energy.rms_db(k, c.start_s, c.end_s) is None
                    and (cu := energy.covered_until(k)) is not None
                    and cu > c.end_s + 0.2
                    and not energy.covers_start(k, c.start_s)
                    for k in (own, other)
                )
                if expired:
                    # Loudness is unjudgeable, but the TEXT test still works —
                    # by expiry the other track has usually transcribed the
                    # span (regression 2026-08-27: emitting unconditionally
                    # produced 6/6 bleed duplicates under cold-start backlog).
                    # Mic side only: bleed flows speakers→mic, never the
                    # reverse, and asymmetry prevents twin-dropping BOTH
                    # copies when both tracks expired. A same-words twin on
                    # the system track → this mic copy is bleed → drop;
                    # otherwise keep (better kept than lost).
                    if own == SourceKind.MIC and find_twin(c, others, cfg.overlap_ratio):
                        continue
                    out.append(AttributedSegment(speaker, c.start_s, c.end_s, c.text))
                else:
                    deferred[own].append(c)
                continue
            # Twin-first (2026-08-27 regression): matching words at matching
            # times on the paired track are near-proof of bleed regardless of
            # a precise loudness gap — mic AGC can shrink the gap below any
            # fixed threshold. Energy only decides the clearly-mic-louder
            # direction (genuine speech), and mic-side only (bleed flows
            # speakers→mic).
            clearly_own_louder = own_db - other_db > cfg.mic_louder_db
            if own == SourceKind.SYSTEM:
                # System side always emits: loopback cannot contain mic bleed.
                out.append(AttributedSegment(speaker, c.start_s, c.end_s, c.text))
                continue
            # mic side from here. ALWAYS wait for the system track's text over
            # this span — even when the mic is clearly louder: a loud segment
            # can be bleed FUSED with genuine speech, and judging before the
            # twin is visible emits the fusion whole (field 2026-08-27, second
            # replay). Chunks interleave, so the wait is ~one worker step.
            if other in tu and tu[other] < c.end_s - 0.5:
                deferred[own].append(c)  # system text pending; don't guess
                continue
            twin_text = find_twin(c, others, cfg.overlap_ratio)
            if twin_text is None:
                out.append(AttributedSegment(speaker, c.start_s, c.end_s, c.text))
                continue
            if clearly_own_louder:
                # Mic is genuinely loud over the span: either the user echoed
                # the words (drop-worthy duplicate) or Whisper FUSED bleed
                # with genuine speech — trim the bleed edge, keep the rest.
                remainder = _trim_twin_edge(c.text, twin_text, cfg.overlap_ratio)
                if remainder:
                    out.append(AttributedSegment(speaker, c.start_s, c.end_s, remainder))
                continue  # full echo/bleed: drop
            continue  # twin + mic not clearly louder: bleed, system owns it

    decide(SourceKind.MIC, mic, system)
    decide(SourceKind.SYSTEM, system, mic)
    out.sort(key=lambda s: (s.start_s, s.source.value))
    return out, deferred
