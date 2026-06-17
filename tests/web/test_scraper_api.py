import types
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.job import Job
from db.database import get_db
from db.database import Base, Config
from scraper.base import ScrapedJob
from web.main import app
import web.routers.scraper as scraper_router


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
    from web.tenancy import current_profile_id
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[current_profile_id] = lambda: 1
    yield TestClient(app)
    app.dependency_overrides.clear()


def _seed_sources(db_session, value: str = "remotive,remoteok") -> None:
    db_session.add(Config(key="scraper_sources", value=value))
    db_session.commit()


def test_trigger_scrape_returns_started(client, db_session, monkeypatch):
    _seed_sources(db_session)

    spawned = []

    class MockThread:
        def __init__(self, **kwargs):
            spawned.append(kwargs)

        def start(self):
            pass

    monkeypatch.setattr(
        scraper_router, "threading",
        types.SimpleNamespace(Thread=MockThread),
        raising=False,
    )

    resp = client.post("/api/scraper/run")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "started"
    assert set(data["sources"]) == {"remotive", "remoteok"}
    assert len(spawned) == 1


def test_trigger_scrape_returns_400_when_no_config_key(client, db_session):
    resp = client.post("/api/scraper/run")
    assert resp.status_code == 400


def test_trigger_scrape_returns_400_when_sources_empty(client, db_session):
    _seed_sources(db_session, value="")
    resp = client.post("/api/scraper/run")
    assert resp.status_code == 400


def test_trigger_scrape_ignores_unknown_source_ids(client, db_session, monkeypatch):
    _seed_sources(db_session, value="remotive,nonexistent")

    spawned = []

    class MockThread:
        def __init__(self, **kwargs):
            spawned.append(kwargs)

        def start(self):
            pass

    monkeypatch.setattr(
        scraper_router, "threading",
        types.SimpleNamespace(Thread=MockThread),
        raising=False,
    )

    resp = client.post("/api/scraper/run")
    assert resp.status_code == 200
    assert resp.json()["sources"] == ["remotive"]


def test_scraper_run_background_calls_intake_on_new_jobs(db_session, monkeypatch):
    fake_scraped = [ScrapedJob(
        source="remotive", job_key="r_bg_1", title="Dev", company="Co",
        url="https://remotive.com/bg1", description="Python dev role.",
        location="Remote", salary="", remote=True, posted_at="2026-01-01",
    )]

    intake_called = []

    def fake_intake(self):
        intake_called.append(self.job_key)

    # Run _run_in_background directly (synchronously) using a real DB session
    with patch.object(Job, "intake", fake_intake), \
         patch.object(scraper_router, "run_scraper",
                      return_value=Job.save_batch_returning(fake_scraped, db_session, 1)), \
         patch.object(scraper_router, "_broadcast", return_value=None), \
         patch.object(scraper_router, "SessionLocal", return_value=db_session):
        scraper_router._run_in_background(["remotive"], 1)

    assert "r_bg_1" in intake_called


def test_stage_job_triggers_pipeline(monkeypatch):
    """run_pipeline is called for each newly staged job."""
    from unittest.mock import patch, MagicMock

    pipeline_calls = []

    with patch("web.routers.scraper.run_pipeline", side_effect=lambda jk, profile_id: pipeline_calls.append((jk, profile_id))) as mock_pipe, \
         patch("web.routers.scraper.Job") as MockJob, \
         patch("web.routers.scraper._sse_send"):

        fake_job = MagicMock()
        fake_job.job_key = "test-key-1"
        MockJob.save_batch_returning.return_value = [fake_job]

        from fastapi.testclient import TestClient
        from web.main import app
        from web.auth.ext_token import bearer_or_session_profile
        app.dependency_overrides[bearer_or_session_profile] = lambda: 1
        c = TestClient(app)
        try:
            resp = c.post("/api/scraper/stage-job", json={
                "source": "linkedin",
                "job_key": "test-key-1",
                "title": "Engineer",
                "company": "Acme",
                "url": "https://example.com/job/1",
                "description": "Do stuff.",
            })
        finally:
            app.dependency_overrides.pop(bearer_or_session_profile, None)

    assert resp.status_code == 200
    mock_pipe.assert_called_once_with("test-key-1", 1)
