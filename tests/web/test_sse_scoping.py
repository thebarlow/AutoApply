"""SSE broadcaster tenant-scoping (audit follow-up).

`/api/events` used to be a global broadcast: every `_sse_send("job", ...)` fanned
a full, tenant-private job payload out to *all* connected clients regardless of
tenant, and (because `job_key` is unique only per profile) could overwrite one
tenant's job row with another's in the recipient's UI. `send`/`subscribe` are now
tenant-scoped; these tests pin that.
"""
import json

import pytest

import web.sse as sse


@pytest.fixture(autouse=True)
def _clean_clients():
    # The broadcaster keeps process-global subscriber state; isolate each test.
    sse._clients.clear()
    yield
    sse._clients.clear()


def _drain(q):
    out = []
    while not q.empty():
        out.append(json.loads(q.get_nowait()))
    return out


def test_scoped_event_reaches_only_its_tenant():
    q1 = sse.subscribe(profile_id=1)
    q2 = sse.subscribe(profile_id=2)
    sse.send("job", {"job_key": "linkedin_1", "title": "A"}, profile_id=1)
    assert [e["data"]["title"] for e in _drain(q1)] == ["A"]
    assert _drain(q2) == []  # tenant 2 never sees tenant 1's job


def test_global_event_reaches_everyone():
    q1 = sse.subscribe(profile_id=1)
    q2 = sse.subscribe(profile_id=2)
    sse.send("llm_status", {"up": True})  # no profile_id → global
    assert len(_drain(q1)) == 1
    assert len(_drain(q2)) == 1


def test_unsubscribe_removes_client():
    q1 = sse.subscribe(profile_id=1)
    sse.unsubscribe(q1)
    sse.send("job", {"job_key": "x"}, profile_id=1)
    assert _drain(q1) == []
