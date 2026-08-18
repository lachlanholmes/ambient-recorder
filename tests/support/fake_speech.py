"""FakeSpeechEngine / FakeEngineFactory (T009) — scripted, model-free.

Scripting: `script[(track, call_index)] = [RawSegment...]` where
call_index counts transcribe() calls per track. Unscripted calls return
[] (silence). Because the worker passes a rolling window, RawSegment
times are relative to the window; helpers below build them from
session-relative times.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict

from ambient_recorder.models.transcript import ReadinessState, TranscriptionReadiness
from ambient_recorder.transcription.protocols import EngineError, EngineNotReadyError, RawSegment


class FakeSpeechEngine:
    descriptor = "fake-engine test/none/cpu"

    def __init__(self) -> None:
        self.script: dict[tuple[str, int], list[RawSegment]] = {}
        self.calls: list[tuple[str, int, int]] = []  # (track, call_index, n_bytes)
        self.modes: list[str] = []  # "live" | "on_demand" per call, in order
        self.delay_s: float = 0.0
        self.fail_after_calls: int | None = None
        self._counts: dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()
        self._current_track: str | None = None

    # The worker tells the fake which track it's about to transcribe (via
    # initial_prompt convention "track=<mic|system>") so scripts can be
    # per-track without changing the SpeechEngine contract.
    def transcribe(self, pcm16k_mono: bytes, *, beam_size: int = 1,
                   initial_prompt: str | None = None) -> list[RawSegment]:
        parts = dict(kv.split("=", 1) for kv in (initial_prompt or "track=mic").split(";"))
        track = parts.get("track", "mic")
        with self._lock:
            idx = self._counts[track]
            self._counts[track] += 1
            self.calls.append((track, idx, len(pcm16k_mono)))
            self.modes.append(parts.get("mode", "live"))
            if self.fail_after_calls is not None and len(self.calls) > self.fail_after_calls:
                raise EngineError("scripted engine failure")
        if self.delay_s:
            time.sleep(self.delay_s)
        return list(self.script.get((track, idx), []))


class FakeEngineFactory:
    def __init__(self, engine: FakeSpeechEngine | None = None,
                 status: ReadinessState = ReadinessState.READY,
                 reason: str | None = None):
        self.engine = engine or FakeSpeechEngine()
        self.status = status
        self.reason = reason
        self.load_calls = 0

    def readiness(self) -> TranscriptionReadiness:
        ready = self.status == ReadinessState.READY
        return TranscriptionReadiness(
            status=self.status, ready=ready,
            engine="fake-engine" if ready else None,
            model="test" if ready else None,
            device="cpu" if ready else None,
            reason=self.reason if not ready else None,
        )

    def load(self):
        self.load_calls += 1
        if self.status != ReadinessState.READY:
            raise EngineNotReadyError(self.readiness())
        return self.engine


def seg(start_s: float, end_s: float, text: str) -> RawSegment:
    return RawSegment(start_s=start_s, end_s=end_s, text=text)
