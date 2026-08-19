"""Real SpeechEngine: faster-whisper / CTranslate2 (T023, gate c).

Import of this module is deliberately lazy (see readiness.DefaultEngineFactory)
so a capture-only install never touches CUDA. On Windows the cuDNN/cuBLAS pip
wheels put their DLLs under site-packages/nvidia/*/bin, which is NOT on the
loader path — we register those directories before ctranslate2 loads its
CUDA backend, so users need no PATH surgery.
"""

from __future__ import annotations

import os
import sys
import sysconfig
from pathlib import Path

import numpy as np

from ambient_recorder.transcription.protocols import EngineError, RawSegment


def _register_nvidia_dll_dirs() -> None:
    if sys.platform != "win32" or not hasattr(os, "add_dll_directory"):
        return
    site = Path(sysconfig.get_paths()["purelib"])
    for sub in ("cudnn", "cublas", "cuda_runtime", "cuda_nvrtc"):
        d = site / "nvidia" / sub / "bin"
        if d.is_dir():
            os.add_dll_directory(str(d))
            os.environ["PATH"] = str(d) + os.pathsep + os.environ.get("PATH", "")


_register_nvidia_dll_dirs()

from faster_whisper import WhisperModel  # noqa: E402  (must follow DLL registration)


class WhisperEngine:
    def __init__(
        self, model: str, device: str, compute_type: str, models_dir: Path, language: str = "en"
    ):
        path = models_dir / model
        if not path.is_dir():
            raise EngineError(f"model directory missing: {path}")
        try:
            self._model = WhisperModel(str(path), device=device, compute_type=compute_type)
        except Exception as e:  # noqa: BLE001 — surface as typed engine failure
            raise EngineError(f"failed to load {model} on {device}/{compute_type}: {e}") from e
        self._descriptor = f"faster-whisper {model}/{compute_type}/{device}"
        self._language = language

    @property
    def descriptor(self) -> str:
        return self._descriptor

    def transcribe(
        self, pcm16k_mono: bytes, *, beam_size: int = 1, initial_prompt: str | None = None
    ) -> list[RawSegment]:
        audio = np.frombuffer(pcm16k_mono, dtype=np.int16).astype(np.float32) / 32768.0
        if len(audio) < 1600:  # < 0.1 s — nothing to say
            return []
        try:
            # initial_prompt from the worker is routing metadata (track=…;mode=…),
            # not a Whisper prompt — do not pass it to the model.
            segments, _info = self._model.transcribe(
                audio,
                beam_size=beam_size,
                language=self._language,
                vad_filter=True,
                condition_on_previous_text=False,
                word_timestamps=False,
            )
            out: list[RawSegment] = []
            for s in segments:
                text = s.text.strip()
                if not text or s.end <= s.start:
                    continue
                out.append(
                    RawSegment(
                        start_s=float(s.start),
                        end_s=float(s.end),
                        text=text,
                        avg_logprob=float(s.avg_logprob),
                    )
                )
            return out
        except Exception as e:  # noqa: BLE001
            raise EngineError(f"transcribe failed: {e}") from e
