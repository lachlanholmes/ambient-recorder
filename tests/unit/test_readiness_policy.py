"""T012: three-way readiness + degradation policy with injected probes."""

from __future__ import annotations

from ambient_recorder.models.transcript import ReadinessState
from ambient_recorder.transcription.readiness import Probes, choose


def _probes(installed=True, free=None, present=()):
    return Probes(lambda: installed, lambda: free, lambda m: m in present)


def test_not_installed():
    r, choice = choose(_probes(installed=False))
    assert r.status == ReadinessState.NOT_INSTALLED and choice is None
    assert "transcription" in r.reason


def test_ready_medium_cuda():
    r, choice = choose(_probes(free=7900, present={"medium", "small"}))
    assert r.status == ReadinessState.READY
    assert choice == ("medium", "cuda", "int8_float16")
    assert r.model == "medium/int8_float16/cuda"


def test_degrades_to_small_cuda_when_vram_tight():
    # Thresholds from gate-(c) measurements: medium needs 1500 MB free.
    r, choice = choose(_probes(free=1200, present={"medium", "small"}))
    assert choice == ("small", "cuda", "int8")


def test_falls_to_cpu_when_vram_very_tight():
    r, choice = choose(_probes(free=500, present={"medium", "small"}))
    assert choice == ("small", "cpu", "int8")


def test_degrades_to_cpu_without_cuda():
    r, choice = choose(_probes(free=None, present={"medium", "small"}))
    assert choice == ("small", "cpu", "int8")
    assert r.device == "cpu"


def test_not_ready_when_model_missing():
    r, choice = choose(_probes(free=7900, present=set()))
    assert r.status == ReadinessState.NOT_READY and choice is None
    assert "model_missing" in r.reason and "fetch_models" in r.reason


def test_medium_missing_but_small_present_uses_small():
    r, choice = choose(_probes(free=7900, present={"small"}))
    assert choice == ("small", "cuda", "int8")
