from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import Base, get_db
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


def _candidate(url: str, key: str, title: str):
    from scraper.base import ScrapedJob
    return ScrapedJob(source="remotive", job_key=key, title=title,
                      company="Acme", url=url, description="d")


def _seed_job(db, profile_id, url, key, state, title):
    db.add(Job(profile_id=profile_id, job_key=key, source="remotive",
               title=title, company="Acme", url=url, description="d",
               state=state))
    db.commit()


def test_search_excludes_scraped_and_applied(client, db_session):
    # profile 1 is the default test tenant (same as stage-job tests).
    # Matching is by candidate_id = hash(title/company/location), so seeded
    # jobs and candidates must share those fields to collide.
    _seed_job(db_session, 1, "https://x.com/applied", "k_app",
              JobState.APPLIED.value, "Applied Eng")
    _seed_job(db_session, 1, "https://x.com/scraped", "k_scr",
              JobState.NEW.value, "Scraped Eng")
    _seed_job(db_session, 1, "https://x.com/deleted", "k_del",
              JobState.DELETED.value, "Deleted Eng")
    cands = [_candidate("https://x.com/applied", "r1", "Applied Eng"),
             _candidate("https://x.com/scraped", "r2", "Scraped Eng"),
             _candidate("https://x.com/deleted", "r3", "Deleted Eng"),
             _candidate("https://x.com/fresh", "r4", "Fresh Eng")]
    with patch("web.routers.scraper.search_sources", return_value=cands):
        resp = client.post("/api/scraper/search", json={"query": "eng"})
    assert resp.status_code == 200
    cs = resp.json()["candidates"]
    # Applied + scraped are hidden; deleted resurfaces; fresh shown.
    assert {c["url"] for c in cs} == {
        "https://x.com/deleted", "https://x.com/fresh",
    }
    # Every survivor carries a stable candidate_id.
    assert all(c.get("candidate_id") for c in cs)


def test_search_persists_query_and_filters(client, db_session):
    with patch("web.routers.scraper.search_sources", return_value=[]) as mock:
        client.post("/api/scraper/search", json={
            "query": "rust dev", "exclude": ["senior", "lead"],
            "location": "USA",
        })
    # filters are forwarded to the source layer
    _, kwargs = mock.call_args
    assert kwargs["exclude"] == ["senior", "lead"]
    assert kwargs["location"] == "USA"
    # and remembered for next time
    assert client.get("/api/scraper/last-search").json() == {
        "query": "rust dev", "exclude": ["senior", "lead"], "location": "USA",
    }


def test_last_search_defaults_empty(client):
    assert client.get("/api/scraper/last-search").json() == {
        "query": "", "exclude": [], "location": "",
    }
