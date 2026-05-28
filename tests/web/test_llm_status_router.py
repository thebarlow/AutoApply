import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import get_db, Base
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


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_llm_status_empty(client):
    resp = client.get("/api/llm-status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["processing"] == []
    assert data["in_flight"] == []


def test_llm_status_in_flight_includes_display_info(client, db_session):
    from web import llm_status
    job = Job(job_key="abc123", source="test", url="https://example.com/jobs/abc123", title="Backend Engineer", company="Acme Corp", state="pending", description="x")
    db_session.add(job)
    db_session.commit()

    llm_status.start("abc123", "score")
    try:
        resp = client.get("/api/llm-status")
        data = resp.json()
        assert len(data["in_flight"]) == 1
        entry = data["in_flight"][0]
        assert entry["job_key"] == "abc123"
        assert entry["title"] == "Backend Engineer"
        assert entry["company"] == "Acme Corp"
        assert "score" in entry["actions"]
    finally:
        llm_status.finish("abc123", "score")
