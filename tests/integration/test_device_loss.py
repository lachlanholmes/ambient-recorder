"""US2 / FR-011: mid-session device loss degrades, never aborts (T023)."""

from __future__ import annotations

import pytest
from tests.support.fake_capture import MIC_ID, SYSTEM_ID

from ambient_recorder.models.api import SessionDetail
from ambient_recorder.models.session import SourceKind


def test_lost_mic_ends_source_session_survives(client, fake_provider):
    sid = client.post("/sessions", json={}).json()["id"]
    fake_provider.push_seconds(MIC_ID, 12.0)
    fake_provider.push_seconds(SYSTEM_ID, 12.0)

    # Covers both real disappearance and default-output-change-as-loss:
    # the T019 poll reports either through this same callback.
    fake_provider.trigger_device_lost(MIC_ID)

    detail = SessionDetail.model_validate(client.get(f"/sessions/{sid}").json())
    assert detail.status == "active"  # survivor keeps recording
    statuses = {s.kind: s.status for s in detail.sources}
    assert statuses[SourceKind.MIC] == "ended_device_lost"
    assert statuses[SourceKind.SYSTEM] == "active"
    lost = [e for e in detail.events if e.type == "device_lost"]
    assert len(lost) == 1
    assert lost[0].detail["kind"] == "mic"
    assert lost[0].detail["device_id"] == MIC_ID
    assert lost[0].detail["last_seq"] == 1  # 12 s → chunks 0 (10 s) + 1 (2 s flush)

    # Survivor still captures; stop finalises normally.
    fake_provider.push_seconds(SYSTEM_ID, 10.0)
    stopped = SessionDetail.model_validate(client.post(f"/sessions/{sid}/stop").json())
    assert stopped.status == "completed"
    assert stopped.duration_s == pytest.approx(22.0, abs=0.1)  # from survivor
    assert stopped.chunk_counts[SourceKind.MIC] == 2
    assert stopped.chunk_counts[SourceKind.SYSTEM] == 3


def test_both_lost_finalises_completed(client, fake_provider):
    sid = client.post("/sessions", json={}).json()["id"]
    fake_provider.push_seconds(MIC_ID, 3.0)
    fake_provider.push_seconds(SYSTEM_ID, 3.0)
    fake_provider.trigger_device_lost(MIC_ID)
    fake_provider.trigger_device_lost(SYSTEM_ID)

    detail = SessionDetail.model_validate(client.get(f"/sessions/{sid}").json())
    # Data-model rule (confirmed): all capturable audio was captured.
    assert detail.status == "completed"
    assert all(s.status == "ended_device_lost" for s in detail.sources)
    assert len([e for e in detail.events if e.type == "device_lost"]) == 2
    assert detail.duration_s == pytest.approx(3.0, abs=0.1)
    # Recorder is ready for a new session afterwards.
    assert client.post("/sessions", json={}).status_code == 201


def test_duplicate_loss_signal_ignored(client, fake_provider):
    sid = client.post("/sessions", json={}).json()["id"]
    fake_provider.trigger_device_lost(MIC_ID)
    fake_provider.trigger_device_lost(MIC_ID)  # second signal is a no-op
    detail = SessionDetail.model_validate(client.get(f"/sessions/{sid}").json())
    assert len([e for e in detail.events if e.type == "device_lost"]) == 1
