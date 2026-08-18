"""In-process segment/status pub/sub (T017). Publishers are the worker
thread; subscribers are WebSocket handlers on the event loop. Each
subscriber owns a bounded queue; a slow subscriber is disconnected rather
than blocking the worker."""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field

from ambient_recorder.models.transcript import SegmentFrame, StatusFrame

Frame = SegmentFrame | StatusFrame
_MAX_BUFFER = 2000
_CLOSE = None


@dataclass
class Subscription:
    transcript_id: str
    q: queue.Queue = field(default_factory=lambda: queue.Queue(maxsize=_MAX_BUFFER))
    dropped: bool = False

    def get(self, timeout: float | None = None) -> Frame | None:
        """Blocking read; None means the stream closed (terminal state or overflow)."""
        return self.q.get(timeout=timeout)


class SegmentStream:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subs: dict[str, list[Subscription]] = {}
        self._latest_status: dict[str, StatusFrame] = {}

    def subscribe(self, transcript_id: str) -> Subscription:
        sub = Subscription(transcript_id)
        with self._lock:
            self._subs.setdefault(transcript_id, []).append(sub)
        return sub

    def unsubscribe(self, sub: Subscription) -> None:
        with self._lock:
            subs = self._subs.get(sub.transcript_id, [])
            if sub in subs:
                subs.remove(sub)

    def latest_status(self, transcript_id: str) -> StatusFrame | None:
        return self._latest_status.get(transcript_id)

    def publish(self, transcript_id: str, frame: Frame) -> None:
        if isinstance(frame, StatusFrame):
            self._latest_status[transcript_id] = frame
        with self._lock:
            subs = list(self._subs.get(transcript_id, []))
        for sub in subs:
            try:
                sub.q.put_nowait(frame)
            except queue.Full:
                sub.dropped = True
                self._close_sub(sub)

    def close(self, transcript_id: str) -> None:
        """Signal end-of-stream to all subscribers of a terminal transcript."""
        with self._lock:
            subs = self._subs.pop(transcript_id, [])
        for sub in subs:
            self._close_sub(sub)

    @staticmethod
    def _close_sub(sub: Subscription) -> None:
        try:
            sub.q.put_nowait(_CLOSE)
        except queue.Full:
            pass
