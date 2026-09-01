"""Real AssistantEngine: Ollama streaming HTTP client (T029, gate c).

Import is lazy (main.py's default factory) so capture-only installs never
touch it. The base URL is loopback-validated in Settings (research R9);
cancellation = the caller stops iterating, which closes the response and
terminates the request server-side.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import httpx

from ambient_recorder.assistant.protocols import EngineError, GenerationChunk


class OllamaEngine:
    def __init__(self, base_url: str, model: str, keep_alive: str = "30m"):
        self._base = base_url.rstrip("/")
        self._model = model
        self._keep_alive = keep_alive
        self._descriptor = f"ollama/{model}"

    @property
    def descriptor(self) -> str:
        return self._descriptor

    def generate(
        self, prompt: str, *, system: str | None = None, max_tokens: int = 1024
    ) -> Iterator[GenerationChunk]:
        payload = {
            "model": self._model,
            "prompt": prompt,
            "stream": True,
            "keep_alive": self._keep_alive,
            # num_ctx: Ollama's default is 4096, which silently truncates
            # summary-map prompts (found live 2026-08-25: 20-min windows
            # overflowed it and the model returned unparseable prose).
            "options": {"num_predict": max_tokens, "temperature": 0.1, "num_ctx": 8192},
        }
        if system:
            payload["system"] = system
        try:
            with httpx.stream(
                "POST", f"{self._base}/api/generate", json=payload,
                timeout=httpx.Timeout(300.0, connect=10.0),
            ) as resp:
                if resp.status_code != 200:
                    resp.read()
                    raise EngineError(f"ollama returned {resp.status_code}: {resp.text[:200]}")
                for line in resp.iter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError as e:
                        raise EngineError(f"malformed stream line: {line[:120]}") from e
                    if data.get("error"):
                        raise EngineError(f"ollama error: {data['error']}")
                    text = data.get("response", "")
                    done = bool(data.get("done"))
                    if text or done:
                        yield GenerationChunk(text=text, done=done)
                    if done:
                        return
        except httpx.HTTPError as e:
            raise EngineError(f"ollama request failed: {e}") from e
