"""T012: three-way assistant readiness with injected probes."""

from __future__ import annotations

from ambient_recorder.assistant.readiness import Probes, choose
from ambient_recorder.models.assistant import AssistantReadinessState


def _probes(version=None, models=()):
    return Probes(lambda: version, lambda m: m in models)


def test_not_installed_when_unreachable():
    r = choose(_probes(version=None), "llama3.2:3b")
    assert r.status == AssistantReadinessState.NOT_INSTALLED
    assert "Ollama" in r.reason


def test_not_ready_when_model_missing():
    r = choose(_probes(version="0.5.0", models={"other:1b"}), "llama3.2:3b")
    assert r.status == AssistantReadinessState.NOT_READY
    assert "ollama pull llama3.2:3b" in r.reason
    assert r.runtime == "ollama 0.5.0"


def test_ready():
    r = choose(_probes(version="0.5.0", models={"llama3.2:3b"}), "llama3.2:3b")
    assert r.status == AssistantReadinessState.READY and r.ready
    assert r.model == "llama3.2:3b"
