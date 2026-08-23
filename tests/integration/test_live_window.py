"""T021: a segment straddling a chunk boundary is emitted exactly once, whole."""

from __future__ import annotations

from tests.conftest import wait_until
from tests.support.fake_capture import MIC_ID, SYSTEM_ID
from tests.support.fake_speech import seg


def test_straddling_segment_emitted_once(app, client, fake_provider, fake_engine):
    # Chunk 0 (session 0–10): engine sees a sentence running past the boundary
    # (8.5 → 10.0 clipped) — must NOT be emitted from this window.
    fake_engine.script[("mic", 0)] = [seg(8.5, 10.0, "we should probably")]
    # Chunk 1 window covers session 5–20; the whole sentence now visible.
    fake_engine.script[("mic", 1)] = [seg(3.5, 7.0, "we should probably ship on friday")]
    fake_engine.script[("system", 0)] = []
    fake_engine.script[("system", 1)] = []

    sid = client.post("/sessions", json={}).json()["id"]
    fake_provider.push_seconds(MIC_ID, 20.0)
    fake_provider.push_seconds(SYSTEM_ID, 20.0)
    assert wait_until(
        lambda: len(client.get(f"/sessions/{sid}/transcript").json()["segments"]) >= 1
    )
    client.post(f"/sessions/{sid}/stop")
    assert wait_until(
        lambda: client.get(f"/sessions/{sid}/transcript").json()["state"] == "completed"
    )

    segs = client.get(f"/sessions/{sid}/transcript").json()["segments"]
    assert [(s["text"], s["start_s"], s["end_s"]) for s in segs] == [
        ("we should probably ship on friday", 8.5, 12.0)
    ]
