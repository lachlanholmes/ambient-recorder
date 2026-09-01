"""Assistant readiness (research R1, analyze/FR-009 layering).

not_installed: Ollama unreachable (capture/transcription-only install) →
assistant endpoints 503 but nothing else is affected.
not_ready: reachable but the configured model is missing → remedy text.
ready: reachable with the model present.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ambient_recorder.models.assistant import AssistantReadiness, AssistantReadinessState


@dataclass
class Probes:
    server_version: Callable[[], str | None]  # None = unreachable
    model_present: Callable[[str], bool]


def default_probes(ollama_url: str) -> Probes:
    import httpx

    def version() -> str | None:
        try:
            r = httpx.get(f"{ollama_url}/api/version", timeout=3.0)
            r.raise_for_status()
            return r.json().get("version")
        except Exception:  # noqa: BLE001 — unreachable is a state, not an error
            return None

    def present(model: str) -> bool:
        try:
            r = httpx.get(f"{ollama_url}/api/tags", timeout=3.0)
            r.raise_for_status()
            names = [m.get("name", "") for m in r.json().get("models", [])]
            # "llama3.2:3b" matches exactly; "llama3.2" matches "llama3.2:latest"
            return any(n == model or n.split(":")[0] == model for n in names)
        except Exception:  # noqa: BLE001
            return False

    return Probes(version, present)


def choose(probes: Probes, model: str) -> AssistantReadiness:
    version = probes.server_version()
    if version is None:
        return AssistantReadiness(
            status=AssistantReadinessState.NOT_INSTALLED,
            ready=False,
            reason=(
                "assistant runtime not reachable: install Ollama "
                "(https://ollama.com) and start it, then `ollama pull <model>`"
            ),
        )
    if not probes.model_present(model):
        return AssistantReadiness(
            status=AssistantReadinessState.NOT_READY,
            ready=False,
            runtime=f"ollama {version}",
            reason=f"model_missing: run `ollama pull {model}`",
        )
    return AssistantReadiness(
        status=AssistantReadinessState.READY,
        ready=True,
        runtime=f"ollama {version}",
        model=model,
    )
