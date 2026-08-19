"""Session capture orchestration (research R6).

Three lanes: capture callbacks enqueue raw frames; one writer thread per
source drains, converts, and persists 10 s chunks; the API layer only
calls start/stop/handle_*. The session belongs to this engine, never to
a client connection (FR-009).
"""

from __future__ import annotations

import queue
import shutil
import threading
import time

from ambient_recorder.audio.protocols import (
    CaptureProvider,
    CaptureStream,
    DeviceEnumerator,
    DeviceUnavailableError,
)
from ambient_recorder.audio.resample import to_pcm16k_mono
from ambient_recorder.config import CHUNK_SECONDS, Settings
from ambient_recorder.errors import (
    DeviceMissingError,
    DiskLowError,
    SessionNotActiveError,
    SessionNotFoundError,
)
from ambient_recorder.logging import jlog
from ambient_recorder.models.api import ReadinessStatus, SessionDetail
from ambient_recorder.models.session import (
    AudioChunk,
    CaptureSource,
    EventType,
    Session,
    SessionEvent,
    SourceKind,
    utcnow,
)
from ambient_recorder.storage.protocols import (
    ActiveSessionExistsError,
    ChunkStore,
    DiskFullError,
    MetadataStore,
)

_SENTINEL = None
# Frames later than this vs. the expected arrival time are treated as a
# silence gap and zero-filled. Well above normal callback jitter (~100 ms
# buffers), well below the shortest gap a human would notice as a timing error.
_GAP_FILL_THRESHOLD_S = 0.5


class _SourceWorker:
    def __init__(self, engine: CaptureEngine, session_id: str, kind: SourceKind, device_id: str):
        self.engine = engine
        self.session_id = session_id
        self.kind = kind
        self.device_id = device_id
        self.stream: CaptureStream | None = None
        self.queue: queue.Queue[bytes | None] = queue.Queue(maxsize=256)
        self.thread = threading.Thread(target=self._run, name=f"writer-{kind.value}", daemon=True)
        self.seq = 0
        self.duration_s = 0.0
        self.ended = threading.Event()

    # capture-thread side -------------------------------------------------

    def on_frames(self, raw: bytes, frame_count: int) -> None:
        if self.ended.is_set():
            return
        self.engine._note_first_frame()
        try:
            self.queue.put_nowait((time.monotonic(), raw))
        except queue.Full:
            jlog("frame_queue_full", kind=self.kind.value, dropped_bytes=len(raw))

    def end_async(self) -> None:
        """Request flush + exit; idempotent."""
        if not self.ended.is_set():
            self.ended.set()
            self.queue.put(_SENTINEL)

    # writer-thread side ---------------------------------------------------

    def _run(self) -> None:
        assert self.stream is not None
        native_chunk_bytes = chunk_byte_target(self.stream.native_rate_hz, self.stream.channels)
        bytes_per_s = self.stream.native_rate_hz * self.stream.channels * 2
        buffer = bytearray()
        # Wall-clock bookkeeping so chunk seq × 10 s is true session time on
        # every track. WASAPI loopback delivers NO frames during output
        # silence, so a track can "lose" minutes of session time; we fill
        # those gaps with zero PCM (real silence on disk) rather than let the
        # two tracks drift onto different clocks. Without this, `them`
        # timestamps are wrong whenever the remote side is quiet and the
        # transcription bleed rule compares the wrong windows.
        # A silent device simply stops delivering frames. Real frames arrive
        # every ~100 ms while audio plays, so idle wall time between two
        # frames beyond the threshold IS the silence (error ≤ one callback
        # period, immaterial at 10 s chunk granularity). The first frame is
        # measured against session start so a late-starting track is padded too.
        # Streams that deliver audio faster than real time (test fakes, file
        # replay) opt out via `realtime = False`; a real device is realtime.
        realtime = getattr(self.stream, "realtime", True)
        last_arrival: float | None = self.engine._session_t0() if realtime else None
        while True:
            item = self.queue.get()
            if item is _SENTINEL:
                self._flush(bytes(buffer))
                return
            arrived_at, raw = item
            if realtime and last_arrival is not None:
                gap_s = arrived_at - last_arrival
                if gap_s > _GAP_FILL_THRESHOLD_S:
                    fill = int(gap_s * bytes_per_s) & ~1  # even byte count (s16)
                    buffer.extend(bytes(fill))
                    jlog("gap_filled", kind=self.kind.value, gap_s=round(gap_s, 2))
            last_arrival = arrived_at
            buffer.extend(raw)
            while len(buffer) >= native_chunk_bytes:
                if not self._flush(bytes(buffer[:native_chunk_bytes])):
                    return
                del buffer[:native_chunk_bytes]

    def _flush(self, native: bytes) -> bool:
        """Convert + persist one chunk. Returns False on disk-full abort."""
        if not native:
            return True
        assert self.stream is not None
        pcm = to_pcm16k_mono(native, self.stream.native_rate_hz, self.stream.channels)
        if not pcm:
            return True
        try:
            meta = self.engine.chunk_store.write_chunk(self.session_id, self.kind, self.seq, pcm)
        except DiskFullError:
            self.ended.set()
            self.engine._on_disk_full(self.kind)
            return False
        self.engine.metadata.record_chunk(
            AudioChunk(
                session_id=self.session_id,
                source_kind=self.kind,
                seq=self.seq,
                file_path=meta.file_path,
                duration_s=meta.duration_s,
                size_bytes=meta.size_bytes,
            )
        )
        self.seq += 1
        self.duration_s += meta.duration_s
        self.engine._notify_chunk(self.session_id, self.kind, meta)
        return True


def chunk_byte_target(native_rate_hz: int, channels: int) -> int:
    """Bytes of native interleaved s16le audio that make one 10 s chunk."""
    return native_rate_hz * channels * 2 * CHUNK_SECONDS


class _ActiveState:
    def __init__(self, session: Session, workers: dict[SourceKind, _SourceWorker]):
        self.session = session
        self.workers = workers
        self.first_frame_logged = False
        self.started_monotonic = time.perf_counter()


class CaptureEngine:
    def __init__(
        self,
        provider: CaptureProvider,
        enumerator: DeviceEnumerator,
        chunk_store: ChunkStore,
        metadata: MetadataStore,
        settings: Settings,
    ):
        self.provider = provider
        self.enumerator = enumerator
        self.chunk_store = chunk_store
        self.metadata = metadata
        self.settings = settings
        self._lock = threading.RLock()
        self._active: _ActiveState | None = None
        self.last_start_latency_s: float | None = None
        self._chunk_observers: list = []
        self._session_observers: list = []

    # -- observers (constitution VII: observers can never hurt capture) ----

    def add_chunk_observer(self, cb) -> None:
        """cb(session_id, kind, ChunkMeta) — invoked on the writer thread
        after the chunk row is committed. Must return quickly (enqueue)."""
        self._chunk_observers.append(cb)

    def add_session_observer(self, cb) -> None:
        """cb(session_id, event) with event in started|stopped|finalized."""
        self._session_observers.append(cb)

    def _notify_chunk(self, session_id: str, kind: SourceKind, meta) -> None:
        for cb in list(self._chunk_observers):
            try:
                cb(session_id, kind, meta)
            except Exception as e:  # noqa: BLE001 — isolation is the point
                jlog("chunk_observer_error", observer=repr(cb), error=repr(e))

    def _notify_session(self, session_id: str, event: str) -> None:
        for cb in list(self._session_observers):
            try:
                cb(session_id, event)
            except Exception as e:  # noqa: BLE001
                jlog("session_observer_error", observer=repr(cb), error=repr(e))

    # -- lifecycle --------------------------------------------------------

    def start_session(self, title: str | None) -> SessionDetail:
        with self._lock:
            if self._active is not None:
                raise ActiveSessionExistsError(self._active.session.id)

            self._preflight()
            devices = {d.kind: d for d in self.enumerator.enumerate()}

            session = Session(title=title, started_at=utcnow(), dir_path="")
            session.dir_path = str(self.settings.sessions_root / session.id)
            workers: dict[SourceKind, _SourceWorker] = {}
            opened: list[CaptureStream] = []
            try:
                for kind in SourceKind:
                    dev = devices[kind]
                    worker = _SourceWorker(self, session.id, kind, dev.id)
                    worker.stream = self.provider.open(
                        dev.id,
                        worker.on_frames,
                        lambda k=kind: self.handle_device_lost(k),
                    )
                    opened.append(worker.stream)
                    workers[kind] = worker
            except DeviceUnavailableError as e:
                for s in opened:
                    s.close()
                raise DeviceMissingError([e.kind]) from e

            sources = [
                CaptureSource(
                    session_id=session.id,
                    kind=kind,
                    device_id=devices[kind].id,
                    device_label=devices[kind].label,
                    native_rate_hz=devices[kind].native_rate_hz,
                )
                for kind in SourceKind
            ]
            try:
                self.metadata.create_active_session(session, sources)
            except Exception:
                for s in opened:
                    s.close()
                raise

            state = _ActiveState(session, workers)
            self._active = state
            for w in workers.values():
                w.thread.start()
            self.metadata.append_event(
                SessionEvent(session_id=session.id, type=EventType.STARTED, detail={"title": title})
            )
            jlog("session_started", session_id=session.id, title=title)
            self._notify_session(session.id, "started")
            detail = self.metadata.get_session(session.id)
            assert detail is not None
            return detail

    def stop_session(self, session_id: str) -> SessionDetail:
        with self._lock:
            self._require_active(session_id)
            self._notify_session(session_id, "stopped")
            self._end_all_sources(final_source_status="completed")
            self._finalize(session_id, EventType.STOPPED, {})
            detail = self.metadata.get_session(session_id)
            assert detail is not None
            return detail

    def handle_device_lost(self, kind: SourceKind) -> None:
        """FR-011: end the lost source, keep the survivor; both lost → completed."""
        with self._lock:
            if self._active is None:
                return
            state = self._active
            worker = state.workers.get(kind)
            if worker is None or worker.ended.is_set():
                return
            worker.stream.close()  # type: ignore[union-attr]
            worker.end_async()
            worker.thread.join(timeout=10)
            self.metadata.end_source(state.session.id, kind, "ended_device_lost", utcnow())
            self.metadata.append_event(
                SessionEvent(
                    session_id=state.session.id,
                    type=EventType.DEVICE_LOST,
                    detail={
                        "kind": kind.value,
                        "device_id": worker.device_id,
                        "last_seq": worker.seq - 1,
                    },
                )
            )
            jlog("device_lost", session_id=state.session.id, kind=kind.value)
            if all(w.ended.is_set() for w in state.workers.values()):
                # Data-model rule: all capturable audio was captured.
                self._finalize(state.session.id, None, {})

    # -- internals --------------------------------------------------------

    def _preflight(self) -> None:
        readiness = self.enumerator.readiness()
        missing = [r.kind for r in readiness if r.status == ReadinessStatus.MISSING]
        if missing:
            raise DeviceMissingError(missing)
        self.settings.data_root.mkdir(parents=True, exist_ok=True)
        free_mb = shutil.disk_usage(self.settings.data_root).free // (1024 * 1024)
        if free_mb < self.settings.min_free_disk_mb:
            raise DiskLowError(int(free_mb), self.settings.min_free_disk_mb)

    def _require_active(self, session_id: str) -> None:
        if self._active is None or self._active.session.id != session_id:
            if self.metadata.get_session(session_id) is None:
                raise SessionNotFoundError(session_id)
            raise SessionNotActiveError(session_id)

    def _end_all_sources(self, final_source_status: str) -> None:
        assert self._active is not None
        state = self._active
        for w in state.workers.values():
            already_ended = w.ended.is_set()
            if w.stream is not None:
                w.stream.close()
            w.end_async()
            w.thread.join(timeout=10)
            if not already_ended:
                self.metadata.end_source(state.session.id, w.kind, final_source_status, utcnow())

    def _finalize(self, session_id: str, event: EventType | None, detail: dict) -> None:
        assert self._active is not None
        state = self._active
        duration = max((w.duration_s for w in state.workers.values()), default=0.0)
        self.metadata.finalize_session(session_id, "completed", utcnow(), duration)
        if event is not None:
            self.metadata.append_event(
                SessionEvent(session_id=session_id, type=event, detail=detail)
            )
        jlog("session_finalized", session_id=session_id, duration_s=duration)
        self._active = None
        self._notify_session(session_id, "finalized")

    def _session_t0(self) -> float | None:
        """Monotonic clock reading at session start (both tracks' time origin)."""
        state = self._active
        return state.started_monotonic if state is not None else None

    def _note_first_frame(self) -> None:
        state = self._active
        if state is None or state.first_frame_logged:
            return
        state.first_frame_logged = True
        self.last_start_latency_s = time.perf_counter() - state.started_monotonic
        jlog(
            "start_latency",
            session_id=state.session.id,
            latency_s=round(self.last_start_latency_s, 3),
        )

    def _on_disk_full(self, kind: SourceKind) -> None:
        """Called from a writer thread; finalise from a fresh thread to
        avoid self-join (research R8 / disk-full edge case)."""

        def finalise() -> None:
            with self._lock:
                if self._active is None:
                    return
                session_id = self._active.session.id
                self.metadata.append_event(
                    SessionEvent(
                        session_id=session_id, type=EventType.DISK_LOW, detail={"kind": kind.value}
                    )
                )
                self._end_all_sources(final_source_status="completed")
                self._finalize(session_id, None, {})
                jlog("session_finalized_disk_full", session_id=session_id)

        threading.Thread(target=finalise, name="disk-full-finalise", daemon=True).start()

    @property
    def active_session_id(self) -> str | None:
        with self._lock:
            return self._active.session.id if self._active else None
