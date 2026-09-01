"""T021: Q&A grounding — citations, decline, ungrounded, follow-ups,
conversation isolation, failure retry."""

from __future__ import annotations

from tests.conftest import wait_until
from tests.support.fake_capture import MIC_ID, SYSTEM_ID
from tests.support.fake_speech import seg


def _finished_session(client, fake_provider, fake_engine, texts) -> str:
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


def _ask_and_wait(client, cid, question, expected_states=("completed", "declined", "ungrounded")):
    client.post(f"/conversations/{cid}/ask", json={"question": question})
    assert wait_until(
        lambda: client.get(f"/conversations/{cid}").json()["turns"][-1]["state"] in expected_states
    )
    return client.get(f"/conversations/{cid}").json()["turns"][-1]


def test_grounded_answer_with_valid_citations(client, fake_provider, fake_engine, fake_llm):
    sid = _finished_session(
        client,
        fake_provider,
        fake_engine,
        ["the certificate problem pushed the release", "ship on thursday"],
    )
    fake_llm.script = [("certificate", "The release was pushed by the certificate problem [1].")]
    cid = client.post("/conversations", json={"session_ids": [sid]}).json()["id"]
    turn = _ask_and_wait(client, cid, "what about the certificate problem?")
    assert turn["state"] == "completed"
    assert turn["citations"] and turn["citations"][0]["session_id"] == sid
    assert turn["watermark"] == "final"


def test_decline_and_ungrounded_paths(client, fake_provider, fake_engine, fake_llm):
    sid = _finished_session(client, fake_provider, fake_engine, ["hello there"])
    cid = client.post("/conversations", json={"session_ids": [sid]}).json()["id"]
    # default response IS the decline phrase
    turn = _ask_and_wait(client, cid, "what about the office move?")
    assert turn["state"] == "declined" and turn["citations"] == []
    # scripted assertion without citations → ungrounded
    fake_llm.script = [("budget", "They approved a nine million budget.")]
    turn = _ask_and_wait(client, cid, "what was the budget?")
    assert turn["state"] == "ungrounded" and turn["citations"] == []


def test_followup_context_and_isolation(client, fake_provider, fake_engine, fake_llm):
    sid = _finished_session(client, fake_provider, fake_engine, ["ship on thursday"])
    c1 = client.post("/conversations", json={"session_ids": [sid]}).json()["id"]
    c2 = client.post("/conversations", json={"session_ids": [sid]}).json()["id"]
    fake_llm.script = [("thursday", "Thursday [1].")]
    _ask_and_wait(client, c1, "when do we ship? thursday?")
    # follow-up in c1: history should appear in the prompt
    fake_llm.script = [("CONVERSATION SO FAR", "They did [1]."), ("thursday", "Thursday [1].")]
    turn = _ask_and_wait(client, c1, "did they confirm it?")
    assert turn["answer"].startswith("They did")
    # same follow-up in fresh c2 has NO history → decline (default response)
    fake_llm.script = []
    turn2 = _ask_and_wait(client, c2, "did they confirm it?")
    assert turn2["state"] == "declined"


def test_engine_failure_then_retry_same_conversation(client, fake_provider, fake_engine, fake_llm):
    sid = _finished_session(client, fake_provider, fake_engine, ["ship on thursday"])
    cid = client.post("/conversations", json={"session_ids": [sid]}).json()["id"]
    fake_llm.fail_after_calls = 0  # first generate raises
    client.post(f"/conversations/{cid}/ask", json={"question": "when?"})
    assert wait_until(
        lambda: client.get(f"/conversations/{cid}").json()["turns"][0]["state"] == "failed"
    )
    fake_llm.fail_after_calls = None
    fake_llm.script = [("thursday", "Thursday [1].")]
    turn = _ask_and_wait(client, cid, "when do we ship? thursday?")
    assert turn["state"] == "completed" and turn["seq"] == 1
