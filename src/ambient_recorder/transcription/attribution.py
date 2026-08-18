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
    bleed_db: float = 6.0  # paired track louder by ≥ this → candidate is bleed
    overlap_ratio: float = 0.6  # ≥ this token overlap with a paired segment → same words
    energy_window_s: float = 30.0


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

    def __init__(self, window_s: float = 30.0):
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


def _tokens(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def _overlap_ratio(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def _time_overlap(a: TimedSegment, b: TimedSegment) -> bool:
    return a.start_s < b.end_s and b.start_s < a.end_s


def attribute(
    mic: list[TimedSegment],
    system: list[TimedSegment],
    energy: EnergyBuffer,
    cfg: AttributionConfig,
) -> tuple[list[AttributedSegment], dict[SourceKind, list[TimedSegment]]]:
    """Returns (attributed, deferred). Deferred candidates lacked paired-track
    energy coverage and must be resubmitted with the next chunk."""
    out: list[AttributedSegment] = []
    deferred: dict[SourceKind, list[TimedSegment]] = {SourceKind.MIC: [], SourceKind.SYSTEM: []}

    def decide(own: SourceKind, cands: list[TimedSegment], others: list[TimedSegment]) -> None:
        other = SourceKind.SYSTEM if own == SourceKind.MIC else SourceKind.MIC
        speaker = Speaker.ME if own == SourceKind.MIC else Speaker.THEM
        for c in cands:
            own_db = energy.rms_db(own, c.start_s, c.end_s)
            other_db = energy.rms_db(other, c.start_s, c.end_s)
            if own_db is None or other_db is None:
                deferred[own].append(c)
                continue
            twin = any(
                _time_overlap(c, o) and _overlap_ratio(c.text, o.text) >= cfg.overlap_ratio
                for o in others
            )
            if twin and other_db - own_db >= cfg.bleed_db:
                continue  # bleed: the paired track owns these words
            out.append(AttributedSegment(speaker, c.start_s, c.end_s, c.text))

    decide(SourceKind.MIC, mic, system)
    decide(SourceKind.SYSTEM, system, mic)
    out.sort(key=lambda s: (s.start_s, s.source.value))
    return out, deferred
