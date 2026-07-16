import json
import unittest.mock as mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import get_db, Base, Account
from core.job import Job, JobState
from core.user import User
from web.main import app
from web.tenancy import current_profile_id


@pytest.fixture
def db_session():
    import core.job  # noqa: F401
    import core.user  # noqa: F401
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
    app.dependency_overrides[current_profile_id] = lambda: 1
    yield TestClient(app)
    app.dependency_overrides.clear()


def _seed_below_floor(db_session):
    """Account for profile 1 with balance below floor; a generatable job."""
    db_session.add(Account(
        id=1, email="below@example.com", profile_id=1,
        created_at="2026-01-01T00:00:00+00:00",
        credit_balance=5, credit_rate=1.5,
    ))
    db_session.add(Job(
        job_key="j1", profile_id=1, source="indeed",
        title="Software Engineer", company="Acme", location="Remote",
        url="https://indeed.com/job/j1", state=JobState.NEW.value,
        description="Build things.",
    ))
    db_session.commit()


def _stub_llm(monkeypatch):
    """Make prompt resolution + client construction succeed so the gate is reached.

    The Job LLM methods are patched to no-ops; if the gate works they are never
    called, but stubbing them keeps the test independent of real LLM behavior.
    """
    fake_user = mock.MagicMock()
    fake_user.prompt_scoring_model = ""
    fake_user.prompt_resume_model = ""
    fake_user.resolve_prompt.return_value = "do the thing"
    monkeypatch.setattr(
        "web.routers.jobs.User.load",
        classmethod(lambda cls, db, profile_id=None: fake_user),
    )
    monkeypatch.setattr(
        "web.routers.jobs.get_client_for_profile",
        lambda user, model=None: (None, "test-model"),
    )
    monkeypatch.setattr(Job, "score", lambda *a, **k: None)
    monkeypatch.setattr(Job, "generate_resume_md", lambda *a, **k: None)
    monkeypatch.setattr(Job, "generate_resume_pdf", lambda *a, **k: None)


def test_score_blocked_when_below_floor(client, db_session, monkeypatch):
    monkeypatch.setenv("CREDIT_FLOOR", "10")
    _seed_below_floor(db_session)
    _stub_llm(monkeypatch)
    r = client.post("/api/jobs/j1/score")
    assert r.status_code == 402
    body = r.json()
    assert body["error"] == "insufficient_credits"
    assert "price" in body and "action" in body


def test_generate_resume_blocked_when_below_floor(client, db_session, monkeypatch):
    monkeypatch.setenv("CREDIT_FLOOR", "10")
    _seed_below_floor(db_session)
    _stub_llm(monkeypatch)
    r = client.post("/api/jobs/j1/generate/resume")
    assert r.status_code == 402
    body = r.json()
    assert body["error"] == "insufficient_credits"
    assert "price" in body and "action" in body
