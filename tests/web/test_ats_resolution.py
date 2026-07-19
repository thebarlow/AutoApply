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
