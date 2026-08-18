"""Engine readiness + degradation policy (research R2/R8, analyze C1).

Three outcomes: not_installed (capture-only install → live mode skipped),
not_ready (installed but unusable → live transcripts fail visibly),
ready (with the model/device the policy chose).
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ambient_recorder.models.transcript import ReadinessState, TranscriptionReadiness

# (model, device, compute_type, min_free_vram_mb) in preference order.
POLICY: list[tuple[str, str, str, int]] = [
    ("medium", "cuda", "int8_float16", 3000),
    ("small", "cuda", "int8", 1500),
    ("small", "cpu", "int8", 0),
]
REQUIRED_VRAM_MB = 2200  # medium steady-state estimate, research R2

FETCH_CMD = "python scripts/fetch_models.py medium"


@dataclass
class Probes:
    installed: Callable[[], bool]
    free_vram_mb: Callable[[], int | None]  # None = no CUDA / cannot probe
    model_present: Callable[[str], bool]


def _default_installed() -> bool:
    return importlib.util.find_spec("faster_whisper") is not None


def _default_free_vram_mb() -> int | None:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    try:
        out = (
            subprocess.run(
                [exe, "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            )
            .stdout.strip()
            .splitlines()[0]
        )
        return int(out)
    except (subprocess.SubprocessError, ValueError, IndexError):
        return None


def default_probes(models_dir: Path) -> Probes:
    def present(name: str) -> bool:
        d = models_dir / name
        return d.is_dir() and any(d.glob("*.bin"))

    return Probes(_default_installed, _default_free_vram_mb, present)


class DefaultEngineFactory:
    """Real factory: readiness via probes; load() imports the Whisper engine
    (gate c) lazily so a capture-only install never touches it."""

    def __init__(self, settings, probes: Probes | None = None):
        self._settings = settings
        self._probes = probes or default_probes(settings.models_dir)
        self._engine = None

    def readiness(self) -> TranscriptionReadiness:
        return choose(self._probes)[0]

    def load(self):
        if self._engine is not None:
            return self._engine
        readiness, choice = choose(self._probes)
        if choice is None:
            from ambient_recorder.transcription.protocols import EngineNotReadyError

            raise EngineNotReadyError(readiness)
        from ambient_recorder.transcription.whisper_engine import WhisperEngine  # gate c

        model, device, compute = choice
        self._engine = WhisperEngine(model, device, compute, self._settings.models_dir)
        return self._engine


def choose(probes: Probes) -> tuple[TranscriptionReadiness, tuple[str, str, str] | None]:
    """Returns (readiness, (model, device, compute_type) | None)."""
    if not probes.installed():
        return TranscriptionReadiness(
            status=ReadinessState.NOT_INSTALLED,
            ready=False,
            reason="transcription extra not installed: pip install -e '.[transcription]'",
        ), None
    free = probes.free_vram_mb()
    for model, device, compute, min_free in POLICY:
        if device == "cuda" and (free is None or free < min_free):
            continue
        if not probes.model_present(model):
            continue
        return TranscriptionReadiness(
            status=ReadinessState.READY,
            ready=True,
            engine="faster-whisper",
            model=f"{model}/{compute}/{device}",
            device=device,  # type: ignore[arg-type]
            free_vram_mb=free,
            required_vram_mb=REQUIRED_VRAM_MB,
        ), (model, device, compute)
    return TranscriptionReadiness(
        status=ReadinessState.NOT_READY,
        ready=False,
        free_vram_mb=free,
        required_vram_mb=REQUIRED_VRAM_MB,
        reason=f"model_missing: run `{FETCH_CMD}` (data/models/ has no usable model)",
    ), None
