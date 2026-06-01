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


def test_skill_frequency_returns_three_lists_and_total(client, db_session):
    _make_extracted_job(db_session, "e1", required="Python, React",
                        preferred="Docker", tech_stack="AWS")
    _make_extracted_job(db_session, "e2", required="Python", seniority="Senior")
    db_session.commit()

    r = client.get("/api/skill-frequency")
    assert r.status_code == 200
    data = r.json()
    assert set(data) == {"required", "preferred", "tech_stack", "total_jobs"}
    assert data["total_jobs"] == 2
    required = {row["skill"]: row["count"] for row in data["required"]}
    assert required["Python"] == 2
    assert required["React"] == 1


def test_skill_frequency_excludes_non_extracted_jobs(client, db_session):
    # Job with no extraction data must not count toward total_jobs.
    _make_extracted_job(db_session, "x1", required="Python")
    _make_job(db_session, "x2", datetime.now(timezone.utc).isoformat())
    db_session.commit()

    r = client.get("/api/skill-frequency")
    data = r.json()
    assert data["total_jobs"] == 1


def test_skill_frequency_empty_db(client):
    r = client.get("/api/skill-frequency")
    assert r.status_code == 200
    data = r.json()
    assert data == {
        "required": [],
        "preferred": [],
        "tech_stack": [],
        "total_jobs": 0,
    }
