"""T018: conversation + ask contracts (top-level, scoped)."""

from __future__ import annotations


def _session(client):
    sid = client.post("/sessions", json={}).json()["id"]
    client.post(f"/sessions/{sid}/stop")
    return sid


def test_create_scope_validation(client):
    sid = _session(client)
    assert client.post("/conversations", json={"session_ids": []}).status_code == 422
    assert client.post("/conversations", json={"session_ids": [sid, sid]}).status_code == 422
    r = client.post("/conversations", json={"session_ids": ["unknown"]})
    assert r.status_code == 404 and r.json()["error"]["code"] == "session_not_found"
    ok = client.post("/conversations", json={"session_ids": [sid]})
    assert ok.status_code == 201
    body = ok.json()
    assert body["session_ids"] == [sid] and body["born_live"] is False


def test_born_live_flag(client):
    sid = client.post("/sessions", json={}).json()["id"]  # active
    c = client.post("/conversations", json={"session_ids": [sid]}).json()
    assert c["born_live"] is True
    client.post(f"/sessions/{sid}/stop")


def test_list_and_get(client):
    s1, s2 = _session(client), _session(client)
    c1 = client.post("/conversations", json={"session_ids": [s1]}).json()["id"]
    c2 = client.post("/conversations", json={"session_ids": [s2]}).json()["id"]
    all_ = client.get("/conversations").json()["conversations"]
    assert [c["id"] for c in all_] == [c2, c1]  # newest first
    filtered = client.get(f"/conversations?session_id={s1}").json()["conversations"]
    assert [c["id"] for c in filtered] == [c1]
    assert client.get(f"/conversations/{c1}").status_code == 200
    r = client.get("/conversations/nope")
    assert r.status_code == 404 and r.json()["error"]["code"] == "conversation_not_found"


def test_ask_validation_and_404(client):
    sid = _session(client)
    cid = client.post("/conversations", json={"session_ids": [sid]}).json()["id"]
    assert client.post("/conversations/nope/ask", json={"question": "hi"}).status_code == 404
    assert client.post(f"/conversations/{cid}/ask", json={"question": ""}).status_code == 422
    assert (
        client.post(f"/conversations/{cid}/ask", json={"question": "x" * 2001}).status_code == 422
    )
    r = client.post(f"/conversations/{cid}/ask", json={"question": "what was said?"})
    assert r.status_code == 202
    assert r.json()["state"] == "streaming" and r.json()["seq"] == 0
