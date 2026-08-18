"""Capture-side Protocols — normative contracts per specs/001 contracts/protocols.md.

Implementations: audio/wasapi.py (real, gate-d), tests/support/fake_capture.py.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from ambient_recorder.models.api import DeviceReadiness
from ambient_recorder.models.session import SourceKind


class DeviceInfo(BaseModel):
    id: str
    label: str
    kind: SourceKind
    is_default: bool
    native_rate_hz: int
    channels: int


class DeviceUnavailableError(Exception):
    def __init__(self, kind: SourceKind, device_id: str | None = None):
        self.kind = kind
        self.device_id = device_id
        super().__init__(f"capture device unavailable: {kind.value}")


# on_frames(raw_pcm_native, frame_count) — called from a capture thread.
FrameCallback = Callable[[bytes, int], None]
# on_device_lost() — fires once when the source can no longer capture
# meaningful audio: device gone, or (system source) default output changed.
DeviceLostCallback = Callable[[], None]


@runtime_checkable
class CaptureStream(Protocol):
    def close(self) -> None:  # idempotent
        ...

    @property
    def native_rate_hz(self) -> int: ...

    @property
    def channels(self) -> int: ...


@runtime_checkable
class CaptureProvider(Protocol):
    def open(
        self,
        device_id: str,
        on_frames: FrameCallback,
        on_device_lost: DeviceLostCallback,
    ) -> CaptureStream: ...


@runtime_checkable
class DeviceEnumerator(Protocol):
    def enumerate(self) -> list[DeviceInfo]: ...

    def readiness(
        self, previous: Mapping[SourceKind, str] | None = None
    ) -> list[DeviceReadiness]: ...
