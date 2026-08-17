"""Fake capture provider/enumerator for device-free tests (T010).

Capabilities: inject frames, refuse devices, trigger mid-stream device
loss (covers both real disappearance and the default-output-change-as-
loss path — the engine sees the same callback either way).
"""

from __future__ import annotations

from collections.abc import Mapping

from ambient_recorder.audio.protocols import (
    DeviceInfo,
    DeviceLostCallback,
    DeviceUnavailableError,
    FrameCallback,
)
from ambient_recorder.models.api import DeviceReadiness, ReadinessStatus
from ambient_recorder.models.session import SourceKind

MIC_ID = "fake-mic"
SYSTEM_ID = "fake-loopback"


class FakeStream:
    def __init__(self, provider: FakeCaptureProvider, device_id: str,
                 on_frames: FrameCallback, on_device_lost: DeviceLostCallback,
                 native_rate_hz: int, channels: int):
        self._provider = provider
        self.device_id = device_id
        self.on_frames = on_frames
        self.on_device_lost = on_device_lost
        self._rate = native_rate_hz
        self._channels = channels
        self.closed = False

    @property
    def native_rate_hz(self) -> int:
        return self._rate

    @property
    def channels(self) -> int:
        return self._channels

    def close(self) -> None:
        self.closed = True


class FakeCaptureProvider:
    def __init__(self, native_rate_hz: int = 48_000,
                 channels: Mapping[str, int] | None = None):
        self.native_rate_hz = native_rate_hz
        self.channels = dict(channels or {MIC_ID: 1, SYSTEM_ID: 2})
        self.refuse: set[str] = set()          # device_ids that fail to open
        self.streams: dict[str, FakeStream] = {}

    def open(self, device_id: str, on_frames: FrameCallback,
             on_device_lost: DeviceLostCallback) -> FakeStream:
        if device_id in self.refuse:
            kind = SourceKind.MIC if device_id == MIC_ID else SourceKind.SYSTEM
            raise DeviceUnavailableError(kind, device_id)
        stream = FakeStream(self, device_id, on_frames, on_device_lost,
                            self.native_rate_hz, self.channels.get(device_id, 1))
        self.streams[device_id] = stream
        return stream

    # -- test controls ---------------------------------------------------

    def push_seconds(self, device_id: str, seconds: float, amplitude: int = 1000) -> None:
        """Inject `seconds` of constant-amplitude native-rate audio."""
        stream = self.streams[device_id]
        frames = int(seconds * stream.native_rate_hz)
        sample = amplitude.to_bytes(2, "little", signed=True)
        stream.on_frames(sample * frames * stream.channels, frames)

    def trigger_device_lost(self, device_id: str) -> None:
        self.streams[device_id].on_device_lost()


class FakeDeviceEnumerator:
    def __init__(self, provider: FakeCaptureProvider,
                 missing: set[SourceKind] | None = None):
        self.provider = provider
        self.missing = missing or set()
        # Mutable so tests can simulate a changed default device.
        self.ids = {SourceKind.MIC: MIC_ID, SourceKind.SYSTEM: SYSTEM_ID}

    def enumerate(self) -> list[DeviceInfo]:
        infos = []
        for kind, dev_id, label in (
            (SourceKind.MIC, self.ids[SourceKind.MIC], "Fake Microphone"),
            (SourceKind.SYSTEM, self.ids[SourceKind.SYSTEM], "Fake Speakers (Loopback)"),
        ):
            if kind not in self.missing:
                infos.append(DeviceInfo(
                    id=dev_id, label=label, kind=kind, is_default=True,
                    native_rate_hz=self.provider.native_rate_hz,
                    channels=self.provider.channels.get(dev_id, 1),
                ))
        return infos

    def readiness(self, previous: Mapping[SourceKind, str] | None = None
                  ) -> list[DeviceReadiness]:
        present = {d.kind: d for d in self.enumerate()}
        out = []
        for kind in SourceKind:
            d = present.get(kind)
            if d is None:
                out.append(DeviceReadiness(kind=kind, status=ReadinessStatus.MISSING))
            elif previous and kind in previous and previous[kind] != d.id:
                out.append(DeviceReadiness(
                    kind=kind, status=ReadinessStatus.DEFAULT_CHANGED,
                    device_id=d.id, device_label=d.label))
            else:
                out.append(DeviceReadiness(
                    kind=kind, status=ReadinessStatus.PRESENT,
                    device_id=d.id, device_label=d.label))
        return out
