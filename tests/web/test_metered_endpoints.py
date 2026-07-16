import unittest.mock as mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import get_db, Base, Account, CreditLedger, PromptDefault
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


def _seed(db_session, balance, **job_kwargs):
    """Account for profile 1 with the given balance; a generatable job."""
    db_session.add(Account(
        id=1, email="acct@example.com", profile_id=1,
        created_at="2026-01-01T00:00:00+00:00",
        credit_balance=balance, credit_rate=1.5,
    ))
    db_session.add(Job(
        job_key="j1", profile_id=1, source="indeed",
        title="Software Engineer", company="Acme", location="Remote",
        url="https://indeed.com/job/j1", state=JobState.NEW.value,
        description="Build things.", **job_kwargs,
    ))
    db_session.commit()


def _stub_llm(monkeypatch):
    """Make prompt resolution + client construction succeed and the Job LLM
    methods no-ops so the metering path is exercised without real LLM calls."""
    fake_user = mock.MagicMock()
    fake_user.prompt_scoring_model = ""
    fake_user.prompt_resume_model = ""
    fake_user.prompt_extraction_model = ""
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
    monkeypatch.setattr(Job, "match_profile_skills", lambda *a, **k: None)
    # Never spawn the background refinement/ATS thread in tests.
    monkeypatch.setattr("web.routers.jobs._spawn", lambda *a, **k: None)


def _debits(db_session):
    return (
        db_session.query(CreditLedger)
        .filter(CreditLedger.reason == "debit")
        .order_by(CreditLedger.id)
        .all()
    )


def _balance(db_session):
    return db_session.query(Account).filter_by(profile_id=1).first().credit_balance


def test_score_debits_one_unit(client, db_session, monkeypatch):
    _seed(db_session, 5)
    _stub_llm(monkeypatch)
    r = client.post("/api/jobs/j1/score")
    assert r.status_code == 200
    assert _balance(db_session) == 4
    debits = _debits(db_session)
    assert len(debits) == 1
    assert debits[0].action == "score"
    assert debits[0].delta == -1


def test_score_blocked_at_zero(client, db_session, monkeypatch):
    _seed(db_session, 0)
    _stub_llm(monkeypatch)
    r = client.post("/api/jobs/j1/score")
    assert r.status_code == 402
    body = r.json()
    assert body["error"] == "insufficient_credits"
    assert body["action"] == "score"
    assert body["price"] == 1
    assert body["balance"] == 0
    assert _debits(db_session) == []


def test_generate_fresh_debits_four_units(client, db_session, monkeypatch):
    _seed(db_session, 5)
    _stub_llm(monkeypatch)
    r = client.post("/api/jobs/j1/generate/resume")
    assert r.status_code == 200
    assert _balance(db_session) == 1
    debits = _debits(db_session)
    assert len(debits) == 1
    assert debits[0].action == "generate_fresh"
    assert debits[0].delta == -4


def test_regenerate_blocked_when_below_price(client, db_session, monkeypatch):
    # A prior render (resume_path set) makes this a regenerate (2u); balance 1 < 2.
    _seed(db_session, 1, resume_path="/tmp/j1_resume.pdf")
    _stub_llm(monkeypatch)
    r = client.post("/api/jobs/j1/generate/resume")
    assert r.status_code == 402
    body = r.json()
    assert body["error"] == "insufficient_credits"
    assert body["action"] == "regenerate"
    assert body["price"] == 2
    assert body["balance"] == 1
    assert _balance(db_session) == 1
    assert _debits(db_session) == []


def test_rematch_debits_one_unit_under_rematch_action(client, db_session, monkeypatch):
    _seed(db_session, 5)
    _stub_llm(monkeypatch)
    db_session.add(PromptDefault(type_key="skill_match", content="match the skills please"))
    db_session.commit()
    r = client.post("/api/jobs/j1/rematch-skills")
    assert r.status_code == 200
    assert _balance(db_session) == 4
    debits = _debits(db_session)
    assert len(debits) == 1
    assert debits[0].action == "rematch"
    assert debits[0].delta == -1
