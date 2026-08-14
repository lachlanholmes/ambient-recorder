# Contract: Internal Provider Protocols

`typing.Protocol` definitions for the swappable seams (constitution II).
Normative code lives in `src/ambient_recorder/audio/protocols.py` and
`src/ambient_recorder/storage/protocols.py`; this document is the
human-readable form. Implementations: WASAPI (real), Fake (tests).

## DeviceEnumerator (audio/protocols.py)

```python
class DeviceEnumerator(Protocol):
    def enumerate(self) -> list[DeviceInfo]:
        """All capture-capable devices: mics and loopback analogues.
        DeviceInfo: id, label, kind (mic|system), is_default, native_rate_hz."""

    def readiness(self) -> list[DeviceReadiness]:
        """FR-005 readiness per source kind (present/missing/default_changed)."""
```

## CaptureProvider (audio/protocols.py)

```python
class CaptureProvider(Protocol):
    def open(self, device_id: str, on_frames: FrameCallback,
             on_device_lost: DeviceLostCallback) -> CaptureStream:
        """Open a capture stream at the device's native rate.
        on_frames(bytes, frame_count) is called from a capture thread.
        on_device_lost() fires once if the device disappears (FR-011).
        Raises DeviceUnavailableError if the device cannot be opened."""

class CaptureStream(Protocol):
    def close(self) -> None: ...   # idempotent
    @property
    def native_rate_hz(self) -> int: ...
    @property
    def channels(self) -> int: ...
```

Conformance tests (REQUIRED): both `WasapiCaptureProvider` (structural
check only in CI — no device open) and `FakeCaptureProvider` satisfy the
Protocols via `isinstance` with `runtime_checkable`; the fake can inject
frames, refuse to open, and simulate device loss mid-stream.

## ChunkStore (storage/protocols.py)

```python
class ChunkStore(Protocol):
    def write_chunk(self, session_id: str, kind: SourceKind, seq: int,
                    pcm16k_mono: bytes) -> ChunkMeta:
        """Write one finalised WAV chunk atomically (.part → rename).
        Returns ChunkMeta(file_path, duration_s, size_bytes).
        Raises DiskFullError on ENOSPC (engine finalises session safely)."""

    def inventory(self, session_id: str, kind: SourceKind) -> list[ChunkMeta]:
        """Finalised chunks on disk, ordered by seq; used by reconciliation.
        Silently removes orphaned .part files."""
```

## MetadataStore (storage/protocols.py)

```python
class MetadataStore(Protocol):
    def create_active_session(self, session: Session,
                              sources: list[CaptureSource]) -> None:
        """Insert atomically; raises ActiveSessionExistsError if another
        session is active (partial unique index)."""

    def record_chunk(self, chunk: AudioChunk) -> None
    def append_event(self, event: SessionEvent) -> None
    def finalize_session(self, session_id: str,
                         status: Literal["completed", "interrupted"],
                         ended_at: datetime, duration_s: float) -> None
    def list_sessions(self) -> list[SessionSummary]
    def get_session(self, session_id: str) -> SessionDetail | None
    def active_sessions(self) -> list[Session]   # reconciliation input
```

All methods are called from the writer thread or (reads) the event loop
via a thread pool; the store serialises writes internally (research R4).
