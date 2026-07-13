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
    job = Job(job_key="abc123", source="test", url="https://example.com/jobs/abc123", title="Backend Engineer", company="Acme Corp", state="pending", description="x", profile_id=1)
    db_session.add(job)
    db_session.commit()

    llm_status.start(1, "abc123", "score")
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
        llm_status.finish(1, "abc123", "score")


def test_llm_status_does_not_leak_other_tenants_jobs(client, db_session):
    from web import llm_status
    from web.tenancy import current_profile_id

    job1 = Job(job_key="job-t1", source="test", url="https://example.com/jobs/job-t1", title="Tenant1 Title", company="Tenant1 Co", state="pending", description="x", profile_id=1)
    job2 = Job(job_key="job-t2", source="test", url="https://example.com/jobs/job-t2", title="Tenant2 Title", company="Tenant2 Co", state="pending", description="x", profile_id=2)
    db_session.add_all([job1, job2])
    db_session.commit()

    llm_status.start(1, "job-t1", "score")
    llm_status.start(2, "job-t2", "score")
    app.dependency_overrides[current_profile_id] = lambda: 1
    try:
        resp = client.get("/api/llm-status")
        data = resp.json()

        entries = {e["job_key"]: e for e in data["in_flight"]}
        assert "job-t1" in entries
        assert entries["job-t1"]["title"] == "Tenant1 Title"
        assert entries["job-t1"]["company"] == "Tenant1 Co"

        # Tenant 2's in-flight op is keyed by (profile_id, job_key), so it must
        # not appear at all in tenant 1's snapshot — not even as a bare job_key.
        assert "job-t2" not in entries
        assert data["processing"] == ["job-t1"]
    finally:
        app.dependency_overrides.pop(current_profile_id, None)
        llm_status.finish(1, "job-t1", "score")
        llm_status.finish(2, "job-t2", "score")
