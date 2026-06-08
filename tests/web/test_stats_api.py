from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import get_db, Base
from core.job import Job
import core.user  # noqa: F401
from web.main import app


@pytest.fixture(autouse=True)
def _clear_skill_cache():
    # The skill-frequency endpoint caches by extracted-job count; reset it so
    # one test's data can't be served to another with the same count.
    from web.routers import stats
    stats._SKILL_CACHE.update(sig=None, ts=0.0, result=None)
    yield


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
    yield TestClient(app)
    app.dependency_overrides.clear()


def _make_job(db, key, scraped_at, state="new", resume_gen=None, cover_gen=None):
    job = Job(
        job_key=key,
        source="test",
        url=f"https://example.com/{key}",
        state=state,
        scraped_at=scraped_at,
        resume_generated_at=resume_gen,
        cover_generated_at=cover_gen,
    )
    db.add(job)
    db.flush()
    return job


def test_stats_all_time_returns_bars_and_by_state(client, db_session):
    now = datetime.now(timezone.utc)
    _make_job(db_session, "j1", now.isoformat(), state="applied",
              resume_gen=now.isoformat(), cover_gen=now.isoformat())
    _make_job(db_session, "j2", now.isoformat(), state="new")
    db_session.commit()

    r = client.get("/api/stats?window=all_time")
    assert r.status_code == 200
    data = r.json()
    assert "bars" in data
    assert "by_state" in data
    total_scraped = sum(b["scraped"] for b in data["bars"])
    assert total_scraped == 2
    total_resumes = sum(b["resumes"] for b in data["bars"])
    assert total_resumes == 1
    total_covers = sum(b["covers"] for b in data["bars"])
    assert total_covers == 1


def test_stats_by_state_counts_correctly(client, db_session):
    now = datetime.now(timezone.utc).isoformat()
    _make_job(db_session, "s1", now, state="new")
    _make_job(db_session, "s2", now, state="new")
    _make_job(db_session, "s3", now, state="applied")
    db_session.commit()

    r = client.get("/api/stats?window=all_time")
    data = r.json()
    assert data["by_state"]["new"] == 2
    assert data["by_state"]["applied"] == 1


def test_stats_today_filters_by_day(client, db_session):
    today = datetime.now(timezone.utc)
    old = (today - timedelta(days=3)).isoformat()
    _make_job(db_session, "t1", today.isoformat(), state="new")
    _make_job(db_session, "t2", old, state="new")
    db_session.commit()

    r = client.get("/api/stats?window=today")
    data = r.json()
    total = sum(b["scraped"] for b in data["bars"])
    assert total == 1


def test_stats_week_filters_last_7_days(client, db_session):
    now = datetime.now(timezone.utc)
    recent = (now - timedelta(days=3)).isoformat()
    old = (now - timedelta(days=10)).isoformat()
    _make_job(db_session, "w1", recent, state="new")
    _make_job(db_session, "w2", old, state="new")
    db_session.commit()

    r = client.get("/api/stats?window=week")
    data = r.json()
    total = sum(b["scraped"] for b in data["bars"])
    assert total == 1


def test_stats_invalid_window_returns_400(client):
    r = client.get("/api/stats?window=bogus")
    assert r.status_code == 400


def test_stats_empty_db_returns_empty_bars(client):
    r = client.get("/api/stats?window=all_time")
    assert r.status_code == 200
    data = r.json()
    assert data["bars"] == []


def _make_extracted_job(db, key, required="", preferred="", tech_stack="",
                        seniority=""):
    job = Job(
        job_key=key,
        source="test",
        url=f"https://example.com/{key}",
        state="new",
        ext_required_skills=required,
        ext_preferred_skills=preferred,
        ext_tech_stack=tech_stack,
        ext_seniority=seniority,
    )
    db.add(job)
    db.flush()
    return job


def test_skill_frequency_returns_unified_shape(client, db_session):
    _make_extracted_job(db_session, "e1", required="Python, React",
                        preferred="Docker", tech_stack="AWS")
    _make_extracted_job(db_session, "e2", required="Python", seniority="Senior")
    db_session.commit()

    r = client.get("/api/skill-frequency")
    assert r.status_code == 200
    data = r.json()
    assert set(data) == {"skills", "categories", "total_jobs", "profile_skills"}
    assert data["total_jobs"] == 2
    skills = {row["skill"]: row for row in data["skills"]}
    assert skills["Python"] == {"skill": "Python", "high": 2, "med": 0, "low": 0, "category": "Languages"}
    assert skills["Docker"] == {"skill": "Docker", "high": 0, "med": 1, "low": 0, "category": "DevOps"}
    assert skills["AWS"] == {"skill": "AWS", "high": 0, "med": 0, "low": 1, "category": "Cloud"}
    cats = {c["category"]: c["count"] for c in data["categories"]}
    assert cats["Languages"] == 2
    assert cats["Frontend"] == 1
    assert cats["DevOps"] == 1
    assert cats["Cloud"] == 1


def test_skill_frequency_excludes_non_extracted_jobs(client, db_session):
    _make_extracted_job(db_session, "x1", required="Python")
    _make_job(db_session, "x2", datetime.now(timezone.utc).isoformat())
    db_session.commit()

    r = client.get("/api/skill-frequency")
    data = r.json()
    assert data["total_jobs"] == 1
    assert {row["skill"] for row in data["skills"]} == {"Python"}


def test_skill_frequency_excludes_deleted_jobs(client, db_session):
    _make_extracted_job(db_session, "d1", required="Python")
    deleted = _make_extracted_job(db_session, "d2", required="Rust")
    deleted.state = "deleted"
    db_session.commit()

    r = client.get("/api/skill-frequency")
    data = r.json()
    assert data["total_jobs"] == 1
    assert {row["skill"] for row in data["skills"]} == {"Python"}


def test_skill_frequency_jobs_excludes_deleted_jobs(client, db_session):
    _make_extracted_job(db_session, "g1", required="Python")
    deleted = _make_extracted_job(db_session, "g2", required="Python")
    deleted.state = "deleted"
    db_session.commit()

    r = client.get("/api/skill-frequency/jobs?skill=Python")
    assert set(r.json()["job_keys"]) == {"g1"}


def test_skill_frequency_empty_db(client):
    r = client.get("/api/skill-frequency")
    assert r.status_code == 200
    assert r.json() == {"skills": [], "categories": [], "total_jobs": 0, "profile_skills": []}


def test_skill_frequency_jobs_returns_matching_keys(client, db_session):
    _make_extracted_job(db_session, "j1", required="Python, React")
    _make_extracted_job(db_session, "j2", tech_stack="Python")
    _make_extracted_job(db_session, "j3", required="Go")
    db_session.commit()

    r = client.get("/api/skill-frequency/jobs?skill=Python")
    assert r.status_code == 200
    assert set(r.json()["job_keys"]) == {"j1", "j2"}


def test_skill_frequency_jobs_matches_via_normalization(client, db_session):
    _make_extracted_job(db_session, "k1", tech_stack="k8s")
    db_session.commit()

    r = client.get("/api/skill-frequency/jobs?skill=Kubernetes")
    assert set(r.json()["job_keys"]) == {"k1"}


def test_skill_frequency_jobs_no_match_returns_empty(client, db_session):
    _make_extracted_job(db_session, "n1", required="Python")
    db_session.commit()

    r = client.get("/api/skill-frequency/jobs?skill=Rust")
    assert r.json()["job_keys"] == []
