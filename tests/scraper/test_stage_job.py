from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import get_db
from db.models import Base, Job
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


_VALID = {
    "source": "linkedin",
    "job_key": "linkedin_123",
    "title": "Software Engineer",
    "company": "Acme Corp",
    "url": "https://www.linkedin.com/jobs/view/123",
    "description": "Build cool stuff.",
    "location": "Remote (US)",
    "remote": True,
    "salary": "",
    "posted_at": "",
    "scraped_at": "2026-04-28T12:00:00Z",
}


def test_stage_job_returns_staged_and_creates_db_record(client, db_session):
    response = client.post("/api/scraper/stage-job", json=_VALID)
    assert response.status_code == 200
    assert response.json() == {"status": "staged", "job_key": "linkedin_123"}
    assert db_session.query(Job).filter_by(job_key="linkedin_123").count() == 1


def test_stage_job_returns_duplicate_for_same_url(client, db_session):
    client.post("/api/scraper/stage-job", json=_VALID)
    payload2 = {**_VALID, "job_key": "linkedin_999"}
    response = client.post("/api/scraper/stage-job", json=payload2)
    assert response.status_code == 200
    assert response.json() == {"status": "duplicate", "job_key": "linkedin_999"}
    assert db_session.query(Job).count() == 1  # still only one record


def test_stage_job_returns_422_for_missing_title(client):
    payload = {k: v for k, v in _VALID.items() if k != "title"}
    response = client.post("/api/scraper/stage-job", json=payload)
    assert response.status_code == 422


def test_stage_job_returns_422_for_missing_url(client):
    payload = {k: v for k, v in _VALID.items() if k != "url"}
    response = client.post("/api/scraper/stage-job", json=payload)
    assert response.status_code == 422
