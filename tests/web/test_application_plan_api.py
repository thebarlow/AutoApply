"""Tests for the application-plan endpoints (compute/persist + fetch)."""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import get_db, Base
from core.job import Job, JobState
from core.user import User
from web.main import app
from web.auth.ext_token import bearer_or_session_profile


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
    app.dependency_overrides[bearer_or_session_profile] = lambda: 1
    yield TestClient(app)
    app.dependency_overrides.clear()


def _seed_user(db_session, profile_id):
    if db_session.query(User).filter_by(id=profile_id).first() is None:
        db_session.add(User(id=profile_id, name=f"Profile {profile_id}", data="{}"))
        db_session.commit()


def _seed_job(db_session, profile_id, job_key, ats_type):
    _seed_user(db_session, profile_id)
    job = Job(
        job_key=job_key,
        profile_id=profile_id,
        source="indeed",
        title="Software Engineer",
        company="Acme",
        location="Remote",
        url=f"https://indeed.com/job/{job_key}",
        state=JobState.NEW.value,
        description="Build things.",
        ats_type=ats_type,
    )
    db_session.add(job)
    db_session.commit()
    return job


def test_post_plan_persists_and_returns(client, db_session):
    _seed_job(db_session, 1, "j1", "greenhouse")
    resp = client.post(
        "/api/scraper/jobs/j1/application-plan", json={"enumerated_fields": []}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["job_key"] == "j1"
    assert any(f["canonical_key"] == "email" for f in body["fields"])
    stored = json.loads(Job.get("j1", db_session, profile_id=1).application_plan)
    assert stored["job_key"] == "j1"


def test_get_plan_returns_stored_and_completeness(client, db_session):
    _seed_job(db_session, 1, "j2", "lever")
    client.post("/api/scraper/jobs/j2/application-plan", json={"enumerated_fields": []})
    resp = client.get("/api/scraper/jobs/j2/application-plan")
    assert resp.status_code == 200
    body = resp.json()
    assert body["plan"]["job_key"] == "j2"
    assert "application_answers_complete" in body


def test_get_plan_null_when_never_computed(client, db_session):
    _seed_job(db_session, 1, "j3", "greenhouse")
    resp = client.get("/api/scraper/jobs/j3/application-plan")
    assert resp.status_code == 200
    body = resp.json()
    assert body["plan"] is None
    assert "application_answers_complete" in body


def test_post_plan_404_for_missing_job(client, db_session):
    resp = client.post("/api/scraper/jobs/nope/application-plan", json={})
    assert resp.status_code == 404


def test_get_plan_404_for_missing_job(client, db_session):
    resp = client.get("/api/scraper/jobs/nope/application-plan")
    assert resp.status_code == 404


def test_cross_tenant_post_cannot_touch_other_job(client, db_session):
    _seed_job(db_session, 2, "other1", "greenhouse")
    resp = client.post("/api/scraper/jobs/other1/application-plan", json={})
    assert resp.status_code == 404


def test_cross_tenant_get_cannot_touch_other_job(client, db_session):
    _seed_job(db_session, 2, "other2", "greenhouse")
    resp = client.get("/api/scraper/jobs/other2/application-plan")
    assert resp.status_code == 404


def test_no_metering_without_essay_pass(client, db_session):
    """A deterministic-only plan (no custom essay fields) must not be metered."""
    from db.database import Account, CreditLedger

    db_session.add(
        Account(
            id=1,
            email="acct@example.com",
            profile_id=1,
            created_at="2026-01-01T00:00:00+00:00",
            credit_balance=5,
            credit_rate=1.5,
        )
    )
    _seed_job(db_session, 1, "j4", "greenhouse")
    db_session.commit()
    resp = client.post(
        "/api/scraper/jobs/j4/application-plan", json={"enumerated_fields": []}
    )
    assert resp.status_code == 200
    balance = db_session.query(Account).filter_by(profile_id=1).first().credit_balance
    assert balance == 5
    debits = db_session.query(CreditLedger).filter(CreditLedger.reason == "debit").all()
    assert debits == []


def test_essay_draft_failure_refunds_and_returns_deterministic_plan(
    client, db_session, monkeypatch
):
    """If the LLM essay pass fails, the map_fields charge is refunded (net zero)
    and a deterministic plan is still returned with the essay field undrafted."""
    from db.database import Account
    import core.job as core_job

    def _boom(user, job, pairs):
        raise RuntimeError("LLM unavailable")

    monkeypatch.setattr(core_job, "draft_application_answers", _boom)

    db_session.add(
        Account(
            id=1,
            email="acct@example.com",
            profile_id=1,
            created_at="2026-01-01T00:00:00+00:00",
            credit_balance=5,
            credit_rate=1.5,
        )
    )
    _seed_job(db_session, 1, "j5", "greenhouse")
    db_session.commit()

    resp = client.post(
        "/api/scraper/jobs/j5/application-plan",
        json={"enumerated_fields": [{"field_id": "q_why", "label": "Why do you want this job?"}]},
    )
    assert resp.status_code == 200
    essay = next(f for f in resp.json()["fields"] if f["field_id"] == "q_why")
    assert essay["status"] == "unknown" and essay["value"] is None
    # Net-zero: debit was refunded, so the balance is unchanged.
    balance = db_session.query(Account).filter_by(profile_id=1).first().credit_balance
    assert balance == 5
