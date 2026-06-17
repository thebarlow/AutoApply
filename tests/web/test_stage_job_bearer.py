"""Tests for stage-job bearer-or-session auth.

Covers:
- Bearer token resolves correct profile_id (happy path).
- Invalid bearer token is rejected with 401 no_account.
- In production env, bearer request bypasses the cookie gate and reaches the route.
"""
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import Base, Account, get_db
from web.main import app, _DEV_SESSION_SECRET
from web.auth import ext_token

PAYLOAD = {
    "source": "indeed",
    "job_key": "indeed_x1",
    "title": "Eng",
    "company": "Acme",
    "url": "https://indeed.com/v/x1",
    "description": "Do.",
}


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    s.add(Account(id=2, email="u@x.com", profile_id=8, created_at="t"))
    s.commit()
    yield s
    s.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_stage_job_with_bearer_uses_token_profile(client, db_session):
    """Bearer token resolves the correct profile_id for the owning account."""
    raw = ext_token.mint_token(db_session, account_id=2)
    captured = {}
    with patch("web.routers.scraper.Job") as MockJob, patch("web.routers.scraper._sse_send"), \
         patch("web.routers.scraper.run_pipeline"):
        job = MagicMock()
        job.job_key = "indeed_x1"

        def _save(batch, db, profile_id):
            captured["profile_id"] = profile_id
            return [job]

        MockJob.save_batch_returning.side_effect = _save
        r = client.post(
            "/api/scraper/stage-job",
            json=PAYLOAD,
            headers={"Authorization": f"Bearer {raw}"},
        )
    assert r.status_code == 200
    assert captured["profile_id"] == 8


def test_stage_job_bad_bearer_rejected(client):
    """An invalid bearer token returns 401 with error=no_account."""
    r = client.post(
        "/api/scraper/stage-job",
        json=PAYLOAD,
        headers={"Authorization": "Bearer bad"},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["error"] == "no_account"


def test_stage_job_bearer_bypasses_cookie_gate_in_prod(monkeypatch, db_session):
    """In production env, a valid bearer request reaches the route (gate does not block it).

    The cookie gate exempts /api/scraper/stage-job; combined with bearer auth this
    means a fully-authed bearer POST must succeed (not 401 from the gate).
    """
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SESSION_SECRET", _DEV_SESSION_SECRET)

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        raw = ext_token.mint_token(db_session, account_id=2)
        with patch("web.routers.scraper.Job") as MockJob, \
             patch("web.routers.scraper._sse_send"), \
             patch("web.routers.scraper.run_pipeline"):
            job = MagicMock()
            job.job_key = "indeed_x1"
            MockJob.save_batch_returning.return_value = [job]
            c = TestClient(app)
            r = c.post(
                "/api/scraper/stage-job",
                json=PAYLOAD,
                headers={"Authorization": f"Bearer {raw}"},
            )
        # Must NOT be 401 from the cookie gate — bearer request reached the route
        assert r.status_code != 401, f"Gate blocked bearer request: {r.json()}"
        assert r.status_code == 200
    finally:
        app.dependency_overrides.clear()
