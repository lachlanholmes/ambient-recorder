"""Transcription worker (research R3/R6, T016/T026/T030).

One thread owns the SpeechEngine. It services a priority queue: live
chunks (0) before on-demand chunks (1); on-demand jobs are chunk-granular
so they yield between chunks. Live mode never skips audio (FR-013): a
backlog only grows the reported lag. Session/chunk observers from the
capture engine only *enqueue*; all work happens here.
"""

from __future__ import annotations

import heapq
import itertools
import threading
import wave
from dataclasses import dataclass, field

from ambient_recorder.config import Settings
from ambient_recorder.logging import jlog
from ambient_recorder.models.session import PERSISTED_SAMPLE_RATE, SourceKind, utcnow
from ambient_recorder.models.transcript import (
    JobState,
    NewSegment,
    ReadinessState,
    SegmentFrame,
    StatusFrame,
    Transcript,
    TranscriptionJob,
    TranscriptMode,
    TranscriptState,
)
from ambient_recorder.storage.protocols import ChunkMeta, ChunkStore
from ambient_recorder.storage.transcripts import SqliteTranscriptStore
from ambient_recorder.transcription.attribution import (
    AttributionConfig,
    EnergyBuffer,
    TimedSegment,
    attribute,
)
from ambient_recorder.transcription.protocols import (
    EngineError,
    EngineFactory,
    EngineNotReadyError,
    SpeechEngine,
)
from ambient_recorder.transcription.stream import SegmentStream

OVERLAP_S = 5.0  # rolling window: new chunk + trailing 5 s of the previous one
_BYTES_PER_S = PERSISTED_SAMPLE_RATE * 2


@dataclass(order=True)
class _Item:
    priority: int
    order: int
    kind: str = field(compare=False)  # "chunk" | "session_stopped" | "on_demand_step" | "shutdown"
    session_id: str = field(compare=False, default="")
    source: SourceKind | None = field(compare=False, default=None)
    meta: ChunkMeta | None = field(compare=False, default=None)
    transcript_id: str = field(compare=False, default="")


@dataclass
class _TrackState:
    tail_pcm: bytes = b""  # trailing OVERLAP_S of the previous chunk
    tail_start_s: float = 0.0  # session time where tail_pcm begins
    next_start_s: float = 0.0  # session time of the next expected chunk
    emitted_until_s: float = 0.0  # segments ending at/before this are already out
    pending: list[TimedSegment] = field(default_factory=list)  # deferred by attribution


@dataclass
class _LiveSession:
    transcript_id: str
    tracks: dict[SourceKind, _TrackState] = field(
        default_factory=lambda: {k: _TrackState() for k in SourceKind}
    )
    energy: EnergyBuffer = field(default_factory=EnergyBuffer)
    stopping: bool = False
    outstanding: int = 0  # chunk items enqueued but not yet processed
    last_chunk_end_s: float = 0.0


class TranscriptionWorker:
    def __init__(
        self,
        factory: EngineFactory,
        store: SqliteTranscriptStore,
        chunk_store: ChunkStore,
        stream: SegmentStream,
        settings: Settings,
    ):
        self.factory = factory
        self.store = store
        self.chunk_store = chunk_store
        self.stream = stream
        self.settings = settings
        self.cfg = AttributionConfig(
            bleed_db=settings.bleed_db, overlap_ratio=settings.overlap_ratio
        )
        self._engine: SpeechEngine | None = None
        self._engine_lock = threading.Lock()
        self._q: list[_Item] = []
        self._qcv = threading.Condition()
        self._counter = itertools.count()
        self._live: dict[str, _LiveSession] = {}
        self._live_lock = threading.Lock()
        # on-demand progress: transcript_id -> (state, inventory, next index)
        self._od_state: dict[str, tuple] = {}
        self._thread = threading.Thread(target=self._run, name="transcription", daemon=True)
        self._stopped = threading.Event()

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        self._thread.start()

    def shutdown(self, timeout: float = 5.0) -> None:
        self._push(_Item(-1, next(self._counter), "shutdown"))
        self._thread.join(timeout=timeout)

    def readiness(self):
        return self.factory.readiness()

    # -- observers (called on capture threads; enqueue only) ---------------

    def on_session_event(self, session_id: str, event: str) -> None:
        if event == "started":
            self._begin_live(session_id)
        elif event == "stopped":
            with self._live_lock:
                live = self._live.get(session_id)
            if live is not None:
                live.stopping = True
                self._push(_Item(0, next(self._counter), "session_stopped", session_id))

    def on_chunk(self, session_id: str, kind: SourceKind, meta: ChunkMeta) -> None:
        with self._live_lock:
            live = self._live.get(session_id)
            if live is None:
                return
            live.outstanding += 1
        self._push(_Item(0, next(self._counter), "chunk", session_id, kind, meta))

    # -- on-demand -----------------------------------------------------------

    def request_on_demand(self, session_id: str) -> Transcript:
        r = self.factory.readiness()
        t = Transcript(
            session_id=session_id,
            mode=TranscriptMode.ON_DEMAND,
            state=TranscriptState.PENDING,
            engine=r.engine,
            model=r.model,
        )
        job = TranscriptionJob(
            transcript_id=t.id,
            session_id=session_id,
            mode=TranscriptMode.ON_DEMAND,
            state=JobState.QUEUED,
            priority=1,
        )
        self.store.create_transcript(t, job)
        self._push(_Item(1, next(self._counter), "on_demand_step", session_id, transcript_id=t.id))
        return t

    def requeue_open_on_demand(self) -> None:
        """After startup reconciliation: put requeued jobs back on the heap."""
        job = self.store.next_queued()
        seen = set()
        while job is not None and job.transcript_id not in seen:
            seen.add(job.transcript_id)
            self._push(
                _Item(
                    1,
                    next(self._counter),
                    "on_demand_step",
                    job.session_id,
                    transcript_id=job.transcript_id,
                )
            )
            job = None  # one step per job; the step re-enqueues itself

    # -- internals -----------------------------------------------------------

    def _push(self, item: _Item) -> None:
        with self._qcv:
            heapq.heappush(self._q, item)
            self._qcv.notify()

    def _begin_live(self, session_id: str) -> None:
        readiness = self.factory.readiness()
        if readiness.status == ReadinessState.NOT_INSTALLED:
            jlog("transcription_skipped", session_id=session_id, reason="not_installed")
            return  # analyze C1: capture-only install → state none, no row
        t = Transcript(
            session_id=session_id,
            mode=TranscriptMode.LIVE,
            state=TranscriptState.LIVE,
            engine=readiness.engine,
            model=readiness.model,
        )
        job = TranscriptionJob(
            transcript_id=t.id,
            session_id=session_id,
            mode=TranscriptMode.LIVE,
            state=JobState.RUNNING,
            priority=0,
            started_at=utcnow(),
            lag_s=0.0,
        )
        if readiness.status != ReadinessState.READY:
            t.state = TranscriptState.FAILED
            t.failure_reason = f"engine_not_ready: {readiness.reason}"
            job.state = JobState.FAILED
            job.failure_reason = t.failure_reason
            job.ended_at = utcnow()
            self.store.create_transcript(t, job)
            jlog("transcription_failed", session_id=session_id, reason=t.failure_reason)
            return
        self.store.create_transcript(t, job)
        with self._live_lock:
            self._live[session_id] = _LiveSession(transcript_id=t.id)
        jlog("transcription_started", session_id=session_id, transcript_id=t.id, mode="live")
        self.stream.publish(t.id, StatusFrame(state=TranscriptState.LIVE, lag_s=0.0))

    def _get_engine(self) -> SpeechEngine:
        with self._engine_lock:
            if self._engine is None:
                self._engine = self.factory.load()
                r = self.factory.readiness()
                jlog(
                    "engine_loaded",
                    descriptor=self._engine.descriptor,
                    model=r.model,
                    device=r.device,
                    free_vram_mb=r.free_vram_mb,
                )
            return self._engine

    def _run(self) -> None:
        try:
            import os

            if hasattr(os, "nice"):
                os.nice(5)  # below-normal priority where supported (research R6)
        except OSError:
            pass
        while True:
            with self._qcv:
                while not self._q:
                    self._qcv.wait()
                item = heapq.heappop(self._q)
            if item.kind == "shutdown":
                self._stopped.set()
                return
            try:
                if item.kind == "chunk":
                    self._process_live_chunk(item)
                elif item.kind == "session_stopped":
                    self._finalise_live(item.session_id)
                elif item.kind == "on_demand_step":
                    self._on_demand_step(item)
            except Exception as e:  # noqa: BLE001 — never let the worker die silently
                jlog("transcription_worker_error", kind=item.kind, error=repr(e))

    # -- live path -----------------------------------------------------------

    def _process_live_chunk(self, item: _Item) -> None:
        with self._live_lock:
            live = self._live.get(item.session_id)
        if live is None or item.source is None or item.meta is None:
            return
        try:
            self._transcribe_chunk(live, item.source, item.meta, beam_size=1)
        except (EngineError, EngineNotReadyError) as e:
            self._fail_live(live, item.session_id, f"engine_error: {e}")
            return
        finally:
            with self._live_lock:
                live.outstanding -= 1
        lag = max(0.0, live.last_chunk_end_s - self._delivered_until(live))
        self.store.update_job(live.transcript_id, lag_s=lag, state=JobState.RUNNING)
        self.stream.publish(live.transcript_id, StatusFrame(state=TranscriptState.LIVE, lag_s=lag))
        jlog("lag_report", transcript_id=live.transcript_id, lag_s=round(lag, 2))
        if live.stopping and live.outstanding == 0:
            self._finalise_live(item.session_id)

    def _transcribe_chunk(
        self,
        live: _LiveSession,
        kind: SourceKind,
        meta: ChunkMeta,
        *,
        beam_size: int,
        mode: str = "live",
    ) -> None:
        engine = self._get_engine()
        with wave.open(meta.file_path, "rb") as w:
            pcm = w.readframes(w.getnframes())
        ts = live.tracks[kind]
        chunk_start = ts.next_start_s
        chunk_dur = len(pcm) / _BYTES_PER_S
        live.energy.add(kind, chunk_start, pcm)

        window_pcm = ts.tail_pcm + pcm
        window_start = ts.tail_start_s if ts.tail_pcm else chunk_start
        raw = engine.transcribe(
            window_pcm, beam_size=beam_size, initial_prompt=f"track={kind.value};mode={mode}"
        )
        # Keep only segments ending after what we've already emitted, and that
        # end inside this chunk (segments still running past its end wait for
        # the next window — pending tail).
        chunk_end = chunk_start + chunk_dur
        cands: list[TimedSegment] = []
        for r in raw:
            s, e = window_start + r.start_s, window_start + r.end_s
            if e <= ts.emitted_until_s + 1e-3 or not r.text.strip():
                continue
            if e > chunk_end - 0.05 and not live.stopping:
                continue  # straddles the boundary → will reappear whole next window
            cands.append(TimedSegment(s, e, r.text.strip()))
        ts.tail_pcm = pcm[-int(OVERLAP_S * _BYTES_PER_S) :]
        ts.tail_start_s = max(chunk_start, chunk_end - OVERLAP_S)
        ts.next_start_s = chunk_end
        live.last_chunk_end_s = max(live.last_chunk_end_s, chunk_end)

        cands = ts.pending + cands
        ts.pending = []
        self._attribute_and_emit(live, kind, cands)
        # This chunk may have supplied the paired-track energy coverage that
        # the OTHER track's deferred candidates were waiting for (analyze U2).
        other = SourceKind.SYSTEM if kind == SourceKind.MIC else SourceKind.MIC
        if live.tracks[other].pending:
            retry = live.tracks[other].pending
            live.tracks[other].pending = []
            self._attribute_and_emit(live, other, retry)

    def _attribute_and_emit(
        self, live: _LiveSession, kind: SourceKind, cands: list[TimedSegment]
    ) -> None:
        if not cands:
            return
        mic = cands if kind == SourceKind.MIC else []
        system = cands if kind == SourceKind.SYSTEM else []
        # For the bleed rule we need the *other* track's candidates that
        # overlap in time; those already emitted are the reference set.
        other_kind = SourceKind.SYSTEM if kind == SourceKind.MIC else SourceKind.MIC
        # Reference set = the other track's emitted segments PLUS its
        # still-pending candidates (a bleed twin may be waiting there too).
        other_recent = self._recent_emitted(live, other_kind, cands) + list(
            live.tracks[other_kind].pending
        )
        if kind == SourceKind.MIC:
            system = other_recent
        else:
            mic = other_recent
        transcribed_until = {k: t.next_start_s for k, t in live.tracks.items()}
        attributed, deferred = attribute(
            mic, system, live.energy, self.cfg, transcribed_until=transcribed_until
        )
        live.tracks[kind].pending = deferred[kind]
        own_speaker = "me" if kind == SourceKind.MIC else "them"
        for a in attributed:
            if a.source.value != own_speaker:
                continue  # only emit this track's own segments; other track emits its own
            seg = self.store.append_segment(
                live.transcript_id,
                NewSegment(source=a.source, start_s=a.start_s, end_s=a.end_s, text=a.text),
            )
            live.tracks[kind].emitted_until_s = max(live.tracks[kind].emitted_until_s, a.end_s)
            self.stream.publish(live.transcript_id, SegmentFrame(segment=seg))
        jlog(
            "segments_emitted",
            transcript_id=live.transcript_id,
            track=kind.value,
            emitted=sum(1 for a in attributed if a.source.value == own_speaker),
            deferred=len(deferred[kind]),
        )

    def _recent_emitted(
        self, live: _LiveSession, kind: SourceKind, around: list[TimedSegment]
    ) -> list[TimedSegment]:
        if not around:
            return []
        lo = min(c.start_s for c in around) - 1.0
        hi = max(c.end_s for c in around) + 1.0
        speaker = "me" if kind == SourceKind.MIC else "them"
        segs = self.store.segments_after(live.transcript_id, -1)
        return [
            TimedSegment(s.start_s, s.end_s, s.text)
            for s in segs
            if s.source.value == speaker and s.start_s < hi and s.end_s > lo
        ]

    def _delivered_until(self, live: _LiveSession) -> float:
        return min(t.emitted_until_s for t in live.tracks.values()) if live.tracks else 0.0

    def _finalise_live(self, session_id: str) -> None:
        with self._live_lock:
            live = self._live.get(session_id)
            if live is None:
                return
            if live.outstanding > 0:
                # Backlog still draining (FR-013): report finalising, wait.
                self.store.update_job(live.transcript_id, state=JobState.FINALISING)
                self.store.set_state(live.transcript_id, TranscriptState.FINALISING)
                self.stream.publish(
                    live.transcript_id,
                    StatusFrame(
                        state=TranscriptState.FINALISING,
                        lag_s=live.last_chunk_end_s - self._delivered_until(live),
                    ),
                )
                return
            del self._live[session_id]
        # Flush any pending candidates regardless of paired-track coverage.
        for kind, ts in live.tracks.items():
            if ts.pending:
                for c in ts.pending:
                    seg = self.store.append_segment(
                        live.transcript_id,
                        NewSegment(
                            source=("me" if kind == SourceKind.MIC else "them"),  # type: ignore[arg-type]
                            start_s=c.start_s,
                            end_s=c.end_s,
                            text=c.text,
                        ),
                    )
                    self.stream.publish(live.transcript_id, SegmentFrame(segment=seg))
                ts.pending = []
        now = utcnow()
        self.store.set_state(
            live.transcript_id, TranscriptState.COMPLETED, final=True, finalised_at=now
        )
        self.store.update_job(live.transcript_id, state=JobState.COMPLETED, ended_at=now, lag_s=0.0)
        self.stream.publish(
            live.transcript_id, StatusFrame(state=TranscriptState.COMPLETED, lag_s=0.0, final=True)
        )
        self.stream.close(live.transcript_id)
        jlog("transcription_finalised", session_id=session_id, transcript_id=live.transcript_id)

    def _fail_live(self, live: _LiveSession, session_id: str, reason: str) -> None:
        with self._live_lock:
            self._live.pop(session_id, None)
        now = utcnow()
        self.store.set_state(live.transcript_id, TranscriptState.FAILED, failure_reason=reason)
        self.store.update_job(
            live.transcript_id, state=JobState.FAILED, ended_at=now, failure_reason=reason
        )
        self.stream.publish(live.transcript_id, StatusFrame(state=TranscriptState.FAILED))
        self.stream.close(live.transcript_id)
        jlog(
            "transcription_failed",
            session_id=session_id,
            transcript_id=live.transcript_id,
            reason=reason,
        )

    # -- on-demand path -----------------------------------------------------

    def _on_demand_step(self, item: _Item) -> None:
        """Process ONE chunk pair of an on-demand job, then re-enqueue at
        priority 1 so live work (priority 0) always interleaves (research R6)."""
        job = self.store.get_job(item.transcript_id)
        if job is None or job.state in (JobState.COMPLETED, JobState.FAILED):
            return
        state = self._od_state.get(item.transcript_id)
        if state is None:
            inv = {k: self.chunk_store.inventory(item.session_id, k) for k in SourceKind}
            total = sum(len(v) for v in inv.values())
            state = _LiveSession(transcript_id=item.transcript_id)
            self._od_state[item.transcript_id] = (state, inv, 0)
            self.store.update_job(
                item.transcript_id,
                state=JobState.RUNNING,
                started_at=utcnow(),
                total_chunks=total,
                progress_chunks=0,
            )
            jlog(
                "transcription_started",
                session_id=item.session_id,
                transcript_id=item.transcript_id,
                mode="on_demand",
                total_chunks=total,
            )
        state, inv, idx = self._od_state[item.transcript_id]
        # Interleave tracks in seq order so energy coverage stays paired.
        order = sorted(
            ((c.seq, k, c) for k, cs in inv.items() for c in cs), key=lambda x: (x[0], x[1].value)
        )
        if idx >= len(order):
            state.stopping = True
            self._finish_on_demand(item, state)
            return
        _, kind, meta = order[idx]
        try:
            self._transcribe_chunk(state, kind, meta, beam_size=5, mode="on_demand")
        except (EngineError, EngineNotReadyError) as e:
            self._od_state.pop(item.transcript_id, None)
            now = utcnow()
            self.store.set_state(
                item.transcript_id, TranscriptState.FAILED, failure_reason=f"engine_error: {e}"
            )
            self.store.update_job(
                item.transcript_id,
                state=JobState.FAILED,
                ended_at=now,
                failure_reason=f"engine_error: {e}",
            )
            jlog("transcription_failed", transcript_id=item.transcript_id, reason=str(e))
            return
        idx += 1
        self._od_state[item.transcript_id] = (state, inv, idx)
        self.store.update_job(item.transcript_id, progress_chunks=idx)
        self._push(
            _Item(
                1,
                next(self._counter),
                "on_demand_step",
                item.session_id,
                transcript_id=item.transcript_id,
            )
        )

    def _finish_on_demand(self, item: _Item, state: _LiveSession) -> None:
        for kind, ts in state.tracks.items():
            for c in ts.pending:
                self.store.append_segment(
                    item.transcript_id,
                    NewSegment(
                        source=("me" if kind == SourceKind.MIC else "them"),  # type: ignore[arg-type]
                        start_s=c.start_s,
                        end_s=c.end_s,
                        text=c.text,
                    ),
                )
            ts.pending = []
        self._od_state.pop(item.transcript_id, None)
        now = utcnow()
        engine = self._engine.descriptor if self._engine else None
        if engine:
            self.store.set_engine(item.transcript_id, engine.split(" ")[0], engine)
        self.store.set_state(
            item.transcript_id, TranscriptState.COMPLETED, final=True, finalised_at=now
        )
        self.store.update_job(item.transcript_id, state=JobState.COMPLETED, ended_at=now)
        jlog("transcription_finalised", transcript_id=item.transcript_id, mode="on_demand")
