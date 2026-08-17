"""Constitution II: implementations satisfy their Protocols structurally."""

from __future__ import annotations

import pytest
from tests.support.fake_capture import MIC_ID, FakeCaptureProvider, FakeDeviceEnumerator

from ambient_recorder.audio.protocols import CaptureProvider, CaptureStream, DeviceEnumerator
from ambient_recorder.config import Settings
from ambient_recorder.storage.chunks import FsChunkStore
from ambient_recorder.storage.metadata import SqliteMetadataStore
from ambient_recorder.storage.protocols import ChunkStore, MetadataStore


def test_fake_provider_conforms():
    provider = FakeCaptureProvider()
    assert isinstance(provider, CaptureProvider)
    assert isinstance(FakeDeviceEnumerator(provider), DeviceEnumerator)
    stream = provider.open(MIC_ID, lambda b, n: None, lambda: None)
    assert isinstance(stream, CaptureStream)


def test_storage_implementations_conform(tmp_path):
    settings = Settings(data_root=tmp_path)
    assert isinstance(FsChunkStore(settings.sessions_root), ChunkStore)
    store = SqliteMetadataStore(settings.db_path)
    try:
        assert isinstance(store, MetadataStore)
    finally:
        store.close()


def test_wasapi_provider_conforms_structurally():
    """CI structural check only — never opens a device (gate d)."""
    wasapi = pytest.importorskip(
        "ambient_recorder.audio.wasapi", reason="WASAPI provider not implemented yet"
    )
    assert isinstance(wasapi.WasapiCaptureProvider, type)
    for method in ("open",):
        assert hasattr(wasapi.WasapiCaptureProvider, method)
    for method in ("enumerate", "readiness"):
        assert hasattr(wasapi.WasapiDeviceEnumerator, method)
