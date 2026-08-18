"""Constitution II: 002 implementations satisfy their Protocols (T009/T023)."""

from __future__ import annotations

import pytest
from tests.support.fake_speech import FakeEngineFactory, FakeSpeechEngine

from ambient_recorder.config import Settings
from ambient_recorder.storage.transcripts import SqliteTranscriptStore
from ambient_recorder.transcription.protocols import EngineFactory, SpeechEngine, TranscriptStore
from ambient_recorder.transcription.readiness import DefaultEngineFactory


def test_fakes_conform():
    assert isinstance(FakeSpeechEngine(), SpeechEngine)
    assert isinstance(FakeEngineFactory(), EngineFactory)


def test_default_factory_conforms(tmp_path):
    assert isinstance(DefaultEngineFactory(Settings(data_root=tmp_path)), EngineFactory)


def test_store_conforms(tmp_path):
    store = SqliteTranscriptStore(tmp_path / "t.sqlite3")
    try:
        assert isinstance(store, TranscriptStore)
    finally:
        store.close()


def test_whisper_engine_conforms_structurally():
    """CI structural check only — never loads a model (gate c)."""
    mod = pytest.importorskip(
        "ambient_recorder.transcription.whisper_engine",
        reason="WhisperEngine not implemented yet (gate c, T023)",
    )
    assert hasattr(mod.WhisperEngine, "transcribe")
    assert hasattr(mod.WhisperEngine, "descriptor")
