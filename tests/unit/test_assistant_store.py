"""T008: store — seq assignment, current selection, priority queue, reconciliation."""

from __future__ import annotations

import pytest

from ambient_recorder.models.assistant import (
    ActionItem,
    AssistantTask,
    Citation,
    Conversation,
    ConversationTurn,
    Summary,
    SummaryContent,
    SummaryItem,
    TaskKind,
    TaskState,
    TurnState,
)
from ambient_recorder.models.transcript import Speaker
from ambient_recorder.storage.assistant import SqliteAssistantStore, reconcile_assistant

CIT = Citation(session_id="s", transcript_id="t", seq=1, start_s=10.0)
CONTENT = SummaryContent(
    overview="o",
    key_points=[SummaryItem(text="k", citations=[CIT])],
    decisions=[],
    action_items=[ActionItem(text="a", owner=Speaker.ME, citations=[CIT])],
)


@pytest.fixture
def store(tmp_path):
    s = SqliteAssistantStore(tmp_path / "a.sqlite3")
    yield s
    s.close()


def _summary(store, session="s") -> Summary:
    s = Summary(session_id=session, transcript_id="t")
    store.create_summary(
        s, AssistantTask(kind=TaskKind.SUMMARY, ref_id=s.id, session_id=session, priority=2)
    )
    return s


def test_summary_versioning_supersede_but_keep(store):
    a = _summary(store)
    store.complete_summary(a.id, CONTENT, "m1")
    b = _summary(store)  # pending re-run
    assert store.current_summary("s").id == a.id  # pending never displaces (002 rule)
    store.fail_summary(b.id, "boom")
    assert store.current_summary("s").id == a.id  # failed never current
    first = _summary(store, session="fresh")  # no completed yet
    assert store.current_summary("fresh").id == first.id  # pending inspectable
    c = _summary(store)
    store.complete_summary(c.id, CONTENT, "m2")
    versions = store.list_summaries("s")
    by_id = {v.id: v for v in versions}
    assert by_id[a.id].superseded is True
    assert by_id[c.id].superseded is False
    assert by_id[b.id].superseded is False  # failed, not superseded


def test_turn_seq_and_conversation_scope(store):
    c = Conversation(session_ids=["s1"])
    store.create_conversation(c)
    for i in range(3):
        t = store.create_turn(
            ConversationTurn(conversation_id=c.id, question=f"q{i}"),
            AssistantTask(kind=TaskKind.ASK, ref_id="x", session_id="s1", priority=1),
        )
        assert t.seq == i
    detail = store.get_conversation(c.id)
    assert detail.session_ids == ["s1"] and len(detail.turns) == 3
    assert store.list_conversations("s1")[0].id == c.id
    assert store.list_conversations("other") == []
    assert len(store.list_conversations()) == 1


def test_answer_streaming_and_finish(store):
    c = Conversation(session_ids=["s"])
    store.create_conversation(c)
    t = store.create_turn(
        ConversationTurn(conversation_id=c.id, question="q"),
        AssistantTask(kind=TaskKind.ASK, ref_id="x", session_id="s", priority=0),
    )
    store.append_answer_text(t.id, "Thur")
    store.append_answer_text(t.id, "sday [2]")
    store.set_turn_answer(t.id, "Thursday [2]")
    store.finish_turn(t.id, TurnState.COMPLETED, [CIT], "final")
    got = store.get_turn(t.id)
    assert got.answer == "Thursday [2]" and got.state == TurnState.COMPLETED
    assert got.citations == [CIT] and got.watermark == "final"


def test_priority_queue_order(store):
    s = _summary(store)  # priority 2
    c = Conversation(session_ids=["s"])
    store.create_conversation(c)
    t = store.create_turn(
        ConversationTurn(conversation_id=c.id, question="live q"),
        AssistantTask(kind=TaskKind.ASK, ref_id="turn", session_id="s", priority=0),
    )
    nxt = store.next_queued()
    assert nxt.kind == TaskKind.ASK and nxt.priority == 0  # live ask outranks summary
    del s, t


def test_reconciliation(store):
    _summary(store)
    c = Conversation(session_ids=["s"])
    store.create_conversation(c)
    draft = ConversationTurn(conversation_id=c.id, question="q")
    turn = store.create_turn(
        draft,
        AssistantTask(kind=TaskKind.ASK, ref_id=draft.id, session_id="s", priority=1),
    )
    store.append_answer_text(turn.id, "partial ans")
    for t in store.open_tasks():  # simulate crash: both mid-flight
        store.update_task(t.id, state=TaskState.RUNNING)
    counts = reconcile_assistant(store)
    assert counts == {"requeued": 1, "interrupted": 1}
    got = store.get_turn(turn.id)
    assert got.state == TurnState.INTERRUPTED
    assert got.answer == "partial ans"  # streamed prefix kept
    assert store.next_queued().kind == TaskKind.SUMMARY  # requeued from scratch
