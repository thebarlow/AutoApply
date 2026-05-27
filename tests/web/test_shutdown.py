import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import get_db, Base
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


@pytest.fixture
def client(db_session, monkeypatch):
    app.dependency_overrides[get_db] = lambda: db_session
    # Patch os._exit so tests don't kill the process
    monkeypatch.setattr("web.routers.shutdown._exit_process", lambda: None)
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_shutdown_immediate_returns_ok(client):
    resp = client.post("/api/shutdown?mode=immediate")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert resp.json()["mode"] == "immediate"


def test_shutdown_wait_returns_ok(client):
    resp = client.post("/api/shutdown?mode=wait")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert resp.json()["mode"] == "wait"
