import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import get_db
from db.database import Base
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
    from web.tenancy import current_profile_id
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[current_profile_id] = lambda: 1
    yield TestClient(app)
    app.dependency_overrides.clear()


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
