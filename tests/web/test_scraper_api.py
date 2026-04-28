import types

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import get_db
from db.models import Base, Config
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


def _seed_sources(db_session, value: str = "remotive,remoteok") -> None:
    db_session.add(Config(key="scraper_sources", value=value))
    db_session.commit()


def test_trigger_scrape_returns_started(client, db_session, monkeypatch):
    import web.routers.scraper as scraper_router
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
    import web.routers.scraper as scraper_router
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
