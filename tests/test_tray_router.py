from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import Base, get_db
from web.main import app

# Ensure ORM models are registered with Base.metadata
import core.job  # noqa: F401
import core.user  # noqa: F401


@pytest.fixture()
def client():
    # StaticPool keeps a single connection alive so in-memory tables persist
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)


def test_apply_endpoint_404_when_job_missing(client):
    resp = client.post("/api/jobs/nonexistent/apply")
    assert resp.status_code == 404


def test_confirm_applied_404_when_job_missing(client):
    resp = client.post("/api/jobs/nonexistent/confirm-applied")
    assert resp.status_code == 404
