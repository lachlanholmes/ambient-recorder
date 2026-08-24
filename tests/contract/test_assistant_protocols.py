"""Constitution II: 003 implementations satisfy their Protocols (T007/T029)."""

from __future__ import annotations

import pytest
from tests.support.fake_assistant import FakeAssistantEngine, FakeAssistantFactory

from ambient_recorder.assistant.protocols import (
    AssistantEngine,
    AssistantEngineFactory,
    AssistantStore,
)
from ambient_recorder.storage.assistant import SqliteAssistantStore


def test_fakes_conform():
    assert isinstance(FakeAssistantEngine(), AssistantEngine)
    assert isinstance(FakeAssistantFactory(), AssistantEngineFactory)


def test_store_conforms(tmp_path):
    store = SqliteAssistantStore(tmp_path / "a.sqlite3")
    try:
        assert isinstance(store, AssistantStore)
    finally:
        store.close()


def test_ollama_engine_conforms_structurally():
    """CI structural check only — never contacts a runtime (gate c)."""
    mod = pytest.importorskip(
        "ambient_recorder.assistant.ollama_engine",
        reason="OllamaEngine not implemented yet (gate c, T029)",
    )
    assert hasattr(mod.OllamaEngine, "generate")
    assert hasattr(mod.OllamaEngine, "descriptor")
