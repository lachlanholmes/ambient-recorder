"""Real capture provider: WASAPI via PyAudioWPatch (T019, gate-d).

- Microphone: default input device.
- System audio: the default output device's WASAPI loopback analogue.
- Device-loss watchdog per stream (research R1 + analyze finding C1):
  polls ~2 s; fires on_device_lost when the stream goes inactive, the
  device vanishes, or — system source — the default output changes
  (a loopback stream would otherwise keep capturing the old, now-silent
  device).

PortAudio caches its device list per PyAudio instance, so polls use a
short-lived instance to see hot-plug changes.
"""

from __future__ import annotations

import threading
from collections.abc import Mapping

import pyaudiowpatch as pyaudio

from ambient_recorder.audio.protocols import (
    DeviceInfo,
    DeviceLostCallback,
    DeviceUnavailableError,
    FrameCallback,
)
from ambient_recorder.logging import jlog
from ambient_recorder.models.api import DeviceReadiness, ReadinessStatus
from ambient_recorder.models.session import SourceKind

_POLL_INTERVAL_S = 2.0
_FRAMES_PER_BUFFER = 4800  # 100 ms at 48 kHz


def _device_id(info: dict) -> str:
    return f"{info['index']}|{info['name']}"


def _snapshot() -> dict[SourceKind, dict]:
    """Fresh view of the two default capture devices; missing kinds absent."""
    found: dict[SourceKind, dict] = {}
    with pyaudio.PyAudio() as pa:
        try:
            mic = pa.get_default_input_device_info()
            if int(mic.get("maxInputChannels", 0)) > 0:
                found[SourceKind.MIC] = dict(mic)
        except OSError:
            pass
        try:
            found[SourceKind.SYSTEM] = dict(pa.get_default_wasapi_loopback())
        except (OSError, LookupError):
            pass
    return found


class WasapiStream:
    def __init__(
        self,
        pa: pyaudio.PyAudio,
        info: dict,
        kind: SourceKind,
        on_frames: FrameCallback,
        on_device_lost: DeviceLostCallback,
    ):
        self._rate = int(info["defaultSampleRate"])
        self._channels = max(1, int(info["maxInputChannels"]))
        self._kind = kind
        self._device_id = _device_id(info)
        self._on_device_lost = on_device_lost
        self._closed = threading.Event()
        self._lost_fired = False

        def callback(in_data, frame_count, time_info, status):
            if in_data and not self._closed.is_set():
                on_frames(in_data, frame_count)
            return (None, pyaudio.paContinue)

        try:
            self._stream = pa.open(
                format=pyaudio.paInt16,
                channels=self._channels,
                rate=self._rate,
                input=True,
                input_device_index=int(info["index"]),
                frames_per_buffer=_FRAMES_PER_BUFFER,
                stream_callback=callback,
            )
        except OSError as e:
            raise DeviceUnavailableError(kind, self._device_id) from e

        self._watchdog = threading.Thread(
            target=self._watch, name=f"watchdog-{kind.value}", daemon=True
        )
        self._watchdog.start()

    @property
    def native_rate_hz(self) -> int:
        return self._rate

    @property
    def channels(self) -> int:
        return self._channels

    def close(self) -> None:
        if self._closed.is_set():
            return
        self._closed.set()
        try:
            self._stream.stop_stream()
            self._stream.close()
        except OSError:
            pass  # stream already dead (e.g. device yanked)

    # -- watchdog ---------------------------------------------------------

    def _watch(self) -> None:
        while not self._closed.wait(_POLL_INTERVAL_S):
            if self._device_gone():
                self._fire_lost()
                return

    def _device_gone(self) -> bool:
        try:
            current = _snapshot().get(self._kind)
            if self._kind == SourceKind.SYSTEM:
                # Default output changed OR loopback vanished → source is
                # no longer capturing what the machine plays (spec edge case).
                if current is None or _device_id(current) != self._device_id:
                    return True
            elif current is None:
                # No default input device left at all.
                return True
            return not self._stream.is_active()
        except OSError:
            return True

    def _fire_lost(self) -> None:
        if self._lost_fired:
            return
        self._lost_fired = True
        jlog("wasapi_device_lost", kind=self._kind.value, device_id=self._device_id)
        self._on_device_lost()


class WasapiCaptureProvider:
    """Keeps one long-lived PyAudio host instance (research R7 pre-warm)."""

    def __init__(self) -> None:
        self._pa = pyaudio.PyAudio()

    def open(
        self,
        device_id: str,
        on_frames: FrameCallback,
        on_device_lost: DeviceLostCallback,
    ) -> WasapiStream:
        for kind, info in _snapshot().items():
            if _device_id(info) == device_id:
                return WasapiStream(self._pa, info, kind, on_frames, on_device_lost)
        kind = SourceKind.SYSTEM if "Loopback" in device_id else SourceKind.MIC
        raise DeviceUnavailableError(kind, device_id)

    def close(self) -> None:
        self._pa.terminate()


class WasapiDeviceEnumerator:
    def __init__(self, provider: WasapiCaptureProvider):
        self._provider = provider

    def enumerate(self) -> list[DeviceInfo]:
        out: list[DeviceInfo] = []
        for kind, info in _snapshot().items():
            out.append(
                DeviceInfo(
                    id=_device_id(info),
                    label=str(info["name"]),
                    kind=kind,
                    is_default=True,
                    native_rate_hz=int(info["defaultSampleRate"]),
                    channels=max(1, int(info["maxInputChannels"])),
                )
            )
        return out

    def readiness(self, previous: Mapping[SourceKind, str] | None = None) -> list[DeviceReadiness]:
        present = {d.kind: d for d in self.enumerate()}
        out: list[DeviceReadiness] = []
        for kind in SourceKind:
            d = present.get(kind)
            if d is None:
                out.append(DeviceReadiness(kind=kind, status=ReadinessStatus.MISSING))
            elif previous and kind in previous and previous[kind] != d.id:
                out.append(
                    DeviceReadiness(
                        kind=kind,
                        status=ReadinessStatus.DEFAULT_CHANGED,
                        device_id=d.id,
                        device_label=d.label,
                    )
                )
            else:
                out.append(
                    DeviceReadiness(
                        kind=kind,
                        status=ReadinessStatus.PRESENT,
                        device_id=d.id,
                        device_label=d.label,
                    )
                )
        return out
