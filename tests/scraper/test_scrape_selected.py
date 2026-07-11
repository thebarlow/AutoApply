from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import Base, get_db
from core.job import Job
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


def _payload(url, key):
    return {"source": "remotive", "job_key": key, "title": "Eng",
            "company": "Acme", "url": url, "description": "d",
            "location": "", "salary": "", "remote": True,
            "posted_at": "", "scraped_at": ""}


def test_scrape_selected_stages_new_jobs(client, db_session):
    body = {"jobs": [_payload("https://x.com/1", "r1"),
                     _payload("https://x.com/2", "r2")]}
    with patch("web.routers.scraper.run_pipeline"):
        resp = client.post("/api/scraper/scrape-selected", json=body)
    assert resp.status_code == 200
    results = {r["job_key"]: r["status"] for r in resp.json()["results"]}
    assert results == {"r1": "staged", "r2": "staged"}
    assert db_session.query(Job).count() == 2


def test_scrape_selected_reports_duplicates(client, db_session):
    body = {"jobs": [_payload("https://x.com/1", "r1")]}
    with patch("web.routers.scraper.run_pipeline"):
        client.post("/api/scraper/scrape-selected", json=body)
        resp = client.post("/api/scraper/scrape-selected", json=body)
    assert resp.json()["results"] == [{"job_key": "r1", "status": "duplicate"}]
    assert db_session.query(Job).count() == 1


def test_scrape_selected_rejects_oversized_batch(client, db_session):
    body = {"jobs": [_payload(f"https://x.com/{i}", f"r{i}") for i in range(26)]}
    with patch("web.routers.scraper.run_pipeline"):
        resp = client.post("/api/scraper/scrape-selected", json=body)
    assert resp.status_code == 400
    assert db_session.query(Job).count() == 0


def test_run_endpoint_is_gone(client):
    # The SPA catch-all mount returns 405 (not 404) for any unmatched POST
    # path, since it only serves GET/HEAD. Either way, POST is no longer
    # routed to the retired scraper.run handler.
    assert client.post("/api/scraper/run").status_code in (404, 405)
