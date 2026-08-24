"""T017: summary pipeline — citations vs real segments, scale tier,
supersede, restart requeue."""

from __future__ import annotations

from fastapi.testclient import TestClient
from tests.conftest import wait_until
from tests.support.fake_capture import MIC_ID, SYSTEM_ID
from tests.support.fake_speech import seg

from ambient_recorder.main import create_app

MAP = (
    "KEY POINTS:\n- release slipped a week [1]\nDECISIONS:\n- ship thursday [2]\n"
    "ACTION ITEMS:\n- me | draft pricing options | by Friday [2]"
)
FINAL = (
    "OVERVIEW: A product review covering the release and pricing.\n"
    "KEY POINTS:\n- release slipped a week [1]\nDECISIONS:\n- ship thursday [2]\n"
    "ACTION ITEMS:\n- me | draft pricing options | by Friday [2]"
)


def _session_with_segments(client, fake_provider, fake_engine, texts) -> str:
    fake_engine.script[("mic", 0)] = [seg(1.0 + i, 1.6 + i, t) for i, t in enumerate(texts)]
    sid = client.post("/sessions", json={}).json()["id"]
    fake_provider.push_seconds(MIC_ID, 10.0)
    fake_provider.push_seconds(SYSTEM_ID, 10.0)
    assert wait_until(
        lambda: len(client.get(f"/sessions/{sid}/transcript").json()["segments"]) >= len(texts)
    )
    client.post(f"/sessions/{sid}/stop")
    assert wait_until(
        lambda: client.get(f"/sessions/{sid}/transcript").json()["state"] == "completed"
    )
    return sid


def test_citations_map_to_real_segments(client, fake_provider, fake_engine, fake_llm):
    fake_llm.script = [("NOTES:", MAP), ("FINAL SUMMARY:", FINAL)]
    sid = _session_with_segments(
        client, fake_provider, fake_engine, ["the release slipped a week", "ship on thursday"]
    )
    client.post(f"/sessions/{sid}/summarize")
    assert wait_until(lambda: client.get(f"/sessions/{sid}/summary").json()["state"] == "completed")
    s = client.get(f"/sessions/{sid}/summary").json()

    transcript = client.get(f"/sessions/{sid}/transcript").json()
    valid_seqs = {x["seq"] for x in transcript["segments"]}
    tid = transcript["id"]
    for group in ("key_points", "decisions"):
        for item in s["content"][group]:
            for c in item["citations"]:
                assert c["seq"] in valid_seqs and c["transcript_id"] == tid
                assert c["session_id"] == sid
    ai = s["content"]["action_items"][0]
    assert ai["owner"] == "me" and ai["deadline_text"] == "by Friday"


def test_resummarize_supersedes_but_keeps(client, fake_provider, fake_engine, fake_llm):
    fake_llm.script = [("NOTES:", MAP), ("FINAL SUMMARY:", FINAL)]
    sid = _session_with_segments(client, fake_provider, fake_engine, ["hello world"])
    client.post(f"/sessions/{sid}/summarize")
    assert wait_until(lambda: client.get(f"/sessions/{sid}/summary").json()["state"] == "completed")
    first = client.get(f"/sessions/{sid}/summary").json()["id"]
    client.post(f"/sessions/{sid}/summarize")
    assert wait_until(
        lambda: client.get(f"/sessions/{sid}/summary").json()["id"] != first
        and client.get(f"/sessions/{sid}/summary").json()["state"] == "completed"
    )
    versions = client.get(f"/sessions/{sid}/summaries").json()["summaries"]
    assert len(versions) == 2
    assert {v["superseded"] for v in versions} == {True, False}
    old = client.get(f"/sessions/{sid}/summaries/{first}").json()
    assert old["state"] == "completed"  # kept, readable


def test_restart_requeues_running_summary(
    settings, fake_provider, enumerator, engine_factory, assistant_factory, fake_llm
):
    fake_llm.script = [("NOTES:", MAP), ("FINAL SUMMARY:", FINAL)]
    with TestClient(
        create_app(settings, fake_provider, enumerator, engine_factory, assistant_factory)
    ) as c1:
        fake_llm.delay_s = 5.0  # summary mid-flight at "crash"

        # reuse helper inline: quick finished session
        engine = assistant_factory.engine  # noqa: F841
        sid = c1.post("/sessions", json={}).json()["id"]
        fake_provider.push_seconds(MIC_ID, 10.0)
        fake_provider.push_seconds(SYSTEM_ID, 10.0)
        c1.post(f"/sessions/{sid}/stop")
        assert wait_until(
            lambda: c1.get(f"/sessions/{sid}/transcript").json()["state"] == "completed"
        )
        r = c1.post(f"/sessions/{sid}/summarize")
        assert r.status_code == 202
        assert wait_until(
            lambda: c1.get(f"/sessions/{sid}/summary").json().get("task_state") == "running"
        )
    fake_llm.delay_s = 0.0
    with TestClient(
        create_app(settings, fake_provider, enumerator, engine_factory, assistant_factory)
    ) as c2:
        assert wait_until(
            lambda: c2.get(f"/sessions/{sid}/summary").json()["state"] == "completed", timeout_s=15
        )
