"""US3 edge: disk-full mid-session finalises safely (T028)."""

from __future__ import annotations

from tests.conftest import wait_until
from tests.support.fake_capture import MIC_ID, SYSTEM_ID

from ambient_recorder.storage.protocols import DiskFullError


class _FullDiskChunkStore:
    """Delegates until armed, then raises DiskFullError on writes."""

    def __init__(self, inner):
        self._inner = inner
        self.full = False

    def write_chunk(self, session_id, kind, seq, pcm16k_mono):
        if self.full:
            raise DiskFullError("simulated ENOSPC")
        return self._inner.write_chunk(session_id, kind, seq, pcm16k_mono)

    def inventory(self, session_id, kind):
        return self._inner.inventory(session_id, kind)


def test_disk_full_mid_session_finalises_cleanly(app, client, fake_provider):
    engine = app.state.engine
    wrapper = _FullDiskChunkStore(engine.chunk_store)
    engine.chunk_store = wrapper

    sid = client.post("/sessions", json={}).json()["id"]
    fake_provider.push_seconds(MIC_ID, 10.5)   # one good chunk persists
    fake_provider.push_seconds(SYSTEM_ID, 10.5)
    # Writer threads persist asynchronously — wait for the good chunk
    # before arming the failure, else the first write already ENOSPCs.
    assert wait_until(
        lambda: client.get(f"/sessions/{sid}").json()["chunk_counts"]["mic"] >= 1
    )

    wrapper.full = True
    fake_provider.push_seconds(MIC_ID, 10.5)   # this write hits ENOSPC

    assert wait_until(
        lambda: engine.active_session_id is None
    ), "disk-full finalise did not run"

    detail = client.get(f"/sessions/{sid}").json()
    assert detail["status"] == "completed"
    assert any(e["type"] == "disk_low" for e in detail["events"])
    # The chunk written before the disk filled is preserved uncorrupted.
    assert detail["chunk_counts"]["mic"] >= 1
