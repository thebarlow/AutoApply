import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import get_db
from db.models import Base, Job
from core.types import JobState
from web.main import app


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def _make_job(
    db_session,
    job_key: str,
    state: JobState,
    final_score: float = 0.75,
    description: str | None = None,
    remote: bool | None = None,
) -> Job:
    job = Job(
        job_key=job_key,
        source="indeed",
        title="Software Engineer",
        company="Acme Corp",
        location="Remote",
        salary="$120,000",
        url=f"https://indeed.com/job/{job_key}",
        state=state.value,
        desirability_score=0.80,
        fit_score=0.70,
        final_score=final_score,
        score_justification=json.dumps({
            "desirability": "Good salary and remote.",
            "fit": "Strong Python match.",
        }),
        description=description,
        remote=remote,
    )
    db_session.add(job)
    db_session.commit()
    return job


# --- GET /api/jobs ---

def test_get_jobs_returns_pending_review(client, db_session):
    _make_job(db_session, "job_a", JobState.PENDING_REVIEW)
    _make_job(db_session, "job_b", JobState.PENDING_REVIEW)
    _make_job(db_session, "job_c", JobState.APPROVED)

    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    keys = [j["job_key"] for j in resp.json()]
    assert "job_a" in keys
    assert "job_b" in keys
    assert "job_c" not in keys


def test_get_jobs_sorted_by_score(client, db_session):
    _make_job(db_session, "low", JobState.PENDING_REVIEW, final_score=0.4)
    _make_job(db_session, "high", JobState.PENDING_REVIEW, final_score=0.9)
    _make_job(db_session, "mid", JobState.PENDING_REVIEW, final_score=0.65)

    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    scores = [j["final_score"] for j in resp.json()]
    assert scores == sorted(scores, reverse=True)


def test_get_jobs_empty(client):
    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_jobs_justification_parsed(client, db_session):
    _make_job(db_session, "job_x", JobState.PENDING_REVIEW)

    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    justification = resp.json()[0]["score_justification"]
    assert isinstance(justification, dict)
    assert "desirability" in justification
    assert "fit" in justification


# --- PATCH /api/jobs/{job_key}/state ---

def test_patch_approve(client, db_session, monkeypatch):
    import types
    import web.routers.jobs as jobs_router

    _make_job(db_session, "job_1", JobState.PENDING_REVIEW)

    class _NoOpThread:
        def __init__(self, **kwargs):
            pass
        def start(self):
            pass

    monkeypatch.setattr(jobs_router, "threading", types.SimpleNamespace(Thread=_NoOpThread), raising=False)

    resp = client.patch("/api/jobs/job_1/state", json={"state": "approved"})
    assert resp.status_code == 200
    assert resp.json()["state"] == "approved"


def test_patch_reject(client, db_session):
    _make_job(db_session, "job_2", JobState.PENDING_REVIEW)

    resp = client.patch("/api/jobs/job_2/state", json={"state": "rejected"})
    assert resp.status_code == 200
    assert resp.json()["state"] == "rejected"


def test_patch_invalid_state(client, db_session):
    _make_job(db_session, "job_3", JobState.PENDING_REVIEW)

    resp = client.patch("/api/jobs/job_3/state", json={"state": "deleted"})
    assert resp.status_code == 400


def test_patch_not_found(client):
    resp = client.patch("/api/jobs/nonexistent/state", json={"state": "approved"})
    assert resp.status_code == 404


def test_approve_spawns_generation_thread(client, db_session, monkeypatch):
    import types
    import web.routers.jobs as jobs_router

    _make_job(db_session, "job_gen", JobState.PENDING_REVIEW)

    spawned = []

    class MockThread:
        def __init__(self, **kwargs):
            spawned.append({"target": kwargs["target"].__name__, "args": kwargs["args"]})

        def start(self):
            pass

    mock_threading = types.SimpleNamespace(Thread=MockThread)
    monkeypatch.setattr(jobs_router, "threading", mock_threading, raising=False)

    resp = client.patch("/api/jobs/job_gen/state", json={"state": "approved"})
    assert resp.status_code == 200
    assert len(spawned) == 1
    assert spawned[0]["target"] == "generate_job"
    assert spawned[0]["args"] == ("job_gen",)


def test_reject_does_not_spawn_thread(client, db_session, monkeypatch):
    import types
    import web.routers.jobs as jobs_router

    _make_job(db_session, "job_rej", JobState.PENDING_REVIEW)

    spawned = []

    class MockThread:
        def __init__(self, **kwargs):
            spawned.append(kwargs)

        def start(self):
            pass

    mock_threading = types.SimpleNamespace(Thread=MockThread)
    monkeypatch.setattr(jobs_router, "threading", mock_threading, raising=False)

    resp = client.patch("/api/jobs/job_rej/state", json={"state": "rejected"})
    assert resp.status_code == 200
    assert len(spawned) == 0


def test_get_jobs_includes_url(client, db_session):
    _make_job(db_session, "job_url", JobState.PENDING_REVIEW)
    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    job = resp.json()[0]
    assert "url" in job
    assert job["url"] == "https://indeed.com/job/job_url"


def test_get_jobs_includes_description(client, db_session):
    _make_job(db_session, "job_desc", JobState.PENDING_REVIEW, description="We are looking for a software engineer.")

    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    job_data = resp.json()[0]
    assert job_data["description"] == "We are looking for a software engineer."


def test_get_jobs_remote_true_when_set(client, db_session):
    _make_job(db_session, "job_remote", JobState.PENDING_REVIEW, remote=True)

    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    job_data = resp.json()[0]
    assert job_data["remote"] is True


def test_get_jobs_remote_none_when_not_set(client, db_session):
    _make_job(db_session, "job_noremote", JobState.PENDING_REVIEW)
    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    job_data = resp.json()[0]
    assert "remote" in job_data
    assert job_data["remote"] is None
