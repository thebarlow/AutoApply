from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import Base, get_db, ProfileConfig
from core.job import Job, JobState
from web.main import app


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def _candidate(url: str, key: str):
    from scraper.base import ScrapedJob
    return ScrapedJob(source="remotive", job_key=key, title="Eng",
                      company="Acme", url=url, description="d")


def _seed_job(db, profile_id, url, key, state):
    db.add(Job(profile_id=profile_id, job_key=key, source="remotive",
               title="Eng", company="Acme", url=url, description="d",
               state=state))
    db.commit()


def test_search_returns_candidates_with_status(client, db_session):
    # profile 1 is the default test tenant (same as stage-job tests)
    _seed_job(db_session, 1, "https://x.com/applied", "k_app",
              JobState.APPLIED.value)
    _seed_job(db_session, 1, "https://x.com/scraped", "k_scr",
              JobState.NEW.value)
    _seed_job(db_session, 1, "https://x.com/deleted", "k_del",
              JobState.DELETED.value)
    cands = [_candidate("https://x.com/applied", "r1"),
             _candidate("https://x.com/scraped", "r2"),
             _candidate("https://x.com/deleted", "r3"),
             _candidate("https://x.com/fresh", "r4")]
    with patch("web.routers.scraper.search_sources", return_value=cands):
        resp = client.post("/api/scraper/search", json={"query": "eng"})
    assert resp.status_code == 200
    by_url = {c["url"]: c["status"] for c in resp.json()["candidates"]}
    assert by_url == {
        "https://x.com/applied": "applied",
        "https://x.com/scraped": "scraped",
        "https://x.com/deleted": "none",
        "https://x.com/fresh": "none",
    }


def test_search_persists_last_query(client, db_session):
    with patch("web.routers.scraper.search_sources", return_value=[]):
        client.post("/api/scraper/search", json={"query": "rust dev"})
    row = db_session.query(ProfileConfig).filter_by(
        profile_id=1, key="last_job_search").first()
    assert row is not None and row.value == "rust dev"
    assert client.get("/api/scraper/last-search").json() == {"query": "rust dev"}


def test_last_search_defaults_empty(client):
    assert client.get("/api/scraper/last-search").json() == {"query": ""}
