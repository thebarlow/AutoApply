"""Tests for ATS-classification persistence through stage-job.

Covers:
- easy_apply=True stages a job with ats_type == "easy_apply".
- easy_apply=False (external) leaves ats_type unset and persists apply_url_raw.
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import get_db
from db.database import Base
from web.main import app
from core.job import Job


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
    from web.auth.ext_token import bearer_or_session_profile

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[bearer_or_session_profile] = lambda: 1
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_stage_job_sets_easy_apply_ats_type(client, db_session):
    with patch("web.routers.scraper.run_pipeline"), patch("web.routers.scraper._sse_send"):
        resp = client.post("/api/scraper/stage-job", json={
            "source": "linkedin", "job_key": "ea1", "title": "T",
            "company": "C", "url": "https://li/ea1", "description": "d",
            "easy_apply": True,
        })
    assert resp.status_code == 200
    job = Job.get("ea1", db_session, profile_id=1)
    assert job.easy_apply is True
    assert job.ats_type == "easy_apply"


def test_stage_job_external_leaves_ats_type_null(client, db_session):
    with patch("web.routers.scraper.run_pipeline"), patch("web.routers.scraper._sse_send"):
        resp = client.post("/api/scraper/stage-job", json={
            "source": "indeed", "job_key": "ex1", "title": "T",
            "company": "C", "url": "https://in/ex1", "description": "d",
            "easy_apply": False, "apply_url_raw": "https://apply/ex1",
        })
    assert resp.status_code == 200
    job = Job.get("ex1", db_session, profile_id=1)
    assert job.easy_apply is False
    assert job.ats_type is None
    assert job.apply_url_raw == "https://apply/ex1"


def _stage_external(client, job_key):
    return client.post("/api/scraper/stage-job", json={
        "source": "linkedin", "job_key": job_key, "title": "T",
        "company": "C", "url": f"https://li/{job_key}", "description": "d",
        "easy_apply": False, "apply_url_raw": "https://li/redir",
    })


def test_ats_resolution_classifies_and_persists(client, db_session):
    _stage_external(client, "r1")
    resp = client.patch("/api/scraper/jobs/r1/ats-resolution", json={
        "apply_url_resolved": "https://boards.greenhouse.io/acme/jobs/9",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["ats_type"] == "greenhouse"
    assert body["ats_domain"] == "boards.greenhouse.io"
    job = Job.get("r1", db_session, profile_id=1)
    assert job.ats_type == "greenhouse"
    assert job.apply_url_resolved == "https://boards.greenhouse.io/acme/jobs/9"


def test_ats_resolution_unknown_job_404(client):
    resp = client.patch("/api/scraper/jobs/nope/ats-resolution", json={
        "apply_url_resolved": "https://x/1",
    })
    assert resp.status_code == 404


# The real target lives in the LinkedIn safety wrapper's url= param. A wrapped
# known ATS is classified at stage time — no tab resolution needed.
def test_stage_job_classifies_linkedin_wrapped_ats(client, db_session):
    wrapped = "https://www.linkedin.com/safety/go/?url=https%3A%2F%2Fjobs.ashbyhq.com%2Fsolace%2Fabc&urlhash=x"
    with patch("web.routers.scraper.run_pipeline"), patch("web.routers.scraper._sse_send"):
        resp = client.post("/api/scraper/stage-job", json={
            "source": "linkedin", "job_key": "w1", "title": "T",
            "company": "C", "url": "https://li/w1", "description": "d",
            "easy_apply": False, "apply_url_raw": wrapped,
        })
    assert resp.status_code == 200
    job = Job.get("w1", db_session, profile_id=1)
    assert job.ats_type == "ashby"
    assert job.ats_domain == "jobs.ashbyhq.com"
    assert job.apply_url_resolved == "https://jobs.ashbyhq.com/solace/abc"


# If the extension stalls on the LinkedIn interstitial and PATCHes that URL,
# resolve_ats falls back to the stored wrapper's true target.
def test_ats_resolution_falls_back_to_wrapped_raw(client, db_session):
    wrapped = "https://www.linkedin.com/safety/go/?url=https%3A%2F%2Fjobs.ashbyhq.com%2Facme%2Fxyz"
    with patch("web.routers.scraper.run_pipeline"), patch("web.routers.scraper._sse_send"):
        client.post("/api/scraper/stage-job", json={
            "source": "linkedin", "job_key": "w2", "title": "T",
            "company": "C", "url": "https://li/w2", "description": "d",
            "easy_apply": False, "apply_url_raw": wrapped,
        })
        resp = client.patch("/api/scraper/jobs/w2/ats-resolution", json={
            "apply_url_resolved": "https://www.linkedin.com/safety/go/?_l=en_US",
        })
    assert resp.status_code == 200
    body = resp.json()
    assert body["ats_type"] == "ashby"
    assert body["ats_domain"] == "jobs.ashbyhq.com"
    assert body["apply_url_resolved"] == "https://jobs.ashbyhq.com/acme/xyz"
