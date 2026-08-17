"""Session endpoint contracts (T014) — every documented status code."""

from __future__ import annotations

from ambient_recorder.models.api import ErrorCode, SessionDetail, SessionListResponse


def test_create_returns_201_active_with_both_sources(client):
    r = client.post("/sessions", json={"title": "Weekly sync"})
    assert r.status_code == 201
    detail = SessionDetail.model_validate(r.json())
    assert detail.status == "active"
    assert detail.title == "Weekly sync"
    assert {s.kind for s in detail.sources} == {"mic", "system"}
    assert all(s.status == "active" for s in detail.sources)


def test_second_create_is_409_already_active(client):
    first = client.post("/sessions", json={}).json()
    r = client.post("/sessions", json={"title": "again"})
    assert r.status_code == 409
    body = r.json()
    assert body["error"]["code"] == ErrorCode.SESSION_ALREADY_ACTIVE
    assert body["error"]["detail"]["active_session_id"] == first["id"]


def test_stop_completes_session(client, fake_provider):
    sid = client.post("/sessions", json={}).json()["id"]
    fake_provider.push_seconds("fake-mic", 2.0)
    fake_provider.push_seconds("fake-loopback", 2.0)
    r = client.post(f"/sessions/{sid}/stop")
    assert r.status_code == 200
    detail = SessionDetail.model_validate(r.json())
    assert detail.status == "completed"
    assert detail.ended_at is not None
    assert all(s.status == "completed" for s in detail.sources)


def test_stop_unknown_is_404(client):
    assert client.post("/sessions/nope/stop").status_code == 404


def test_stop_twice_is_409_not_active(client):
    sid = client.post("/sessions", json={}).json()["id"]
    client.post(f"/sessions/{sid}/stop")
    r = client.post(f"/sessions/{sid}/stop")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == ErrorCode.SESSION_NOT_ACTIVE


def test_list_is_newest_first(client):
    a = client.post("/sessions", json={"title": "a"}).json()["id"]
    client.post(f"/sessions/{a}/stop")
    b = client.post("/sessions", json={"title": "b"}).json()["id"]
    client.post(f"/sessions/{b}/stop")
    listed = SessionListResponse.model_validate(client.get("/sessions").json())
    assert [s.id for s in listed.sessions] == [b, a]


def test_inspect_shape(client, fake_provider):
    sid = client.post("/sessions", json={}).json()["id"]
    fake_provider.push_seconds("fake-mic", 1.0)
    client.post(f"/sessions/{sid}/stop")
    detail = SessionDetail.model_validate(client.get(f"/sessions/{sid}").json())
    assert set(detail.chunk_counts.keys()) == {"mic", "system"}
    assert [e.type for e in detail.events][0] == "started"
    assert detail.events[-1].type == "stopped"
