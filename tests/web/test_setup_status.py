import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import get_db, Base, Config
from core.user import User
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


def test_setup_status_returns_booleans(client):
    r = client.get("/api/setup-status")
    assert r.status_code == 200
    data = r.json()
    assert "llm_configured" in data
    assert "resume_parsed" in data
    assert isinstance(data["llm_configured"], bool)
    assert isinstance(data["resume_parsed"], bool)


def test_setup_status_llm_not_configured_initially(client, db_session, monkeypatch):
    """llm_configured should be False when no providers exist.

    Isolated from the developer's real .env / LLM_API_KEY so the result depends
    only on the (empty) test DB.
    """
    from unittest import mock

    monkeypatch.delenv("LLM_API_KEY", raising=False)
    with mock.patch("web.routers.setup_status._read_env", return_value={}):
        r = client.get("/api/setup-status")
    assert r.status_code == 200
    assert r.json()["llm_configured"] is False


def test_setup_status_resume_not_parsed_initially(client, db_session):
    """resume_parsed should be False when profile has no structured data."""
    r = client.get("/api/setup-status")
    assert r.status_code == 200
    assert r.json()["resume_parsed"] is False


def test_setup_status_llm_configured_when_provider_exists(client, db_session):
    """llm_configured should be True when a provider with an API key exists."""
    # Create a provider with a key
    providers = [{"id": "test-provider", "name": "Test", "provider_type": "openai", "default_model": "gpt-4"}]
    db_session.add(Config(key="named_providers", value=json.dumps(providers)))
    db_session.commit()

    # Mock the .env file to have a key for this provider
    import tempfile
    from pathlib import Path
    from unittest import mock

    env_content = "LLM_KEY_TEST_PROVIDER=sk-test-key\n"

    with mock.patch("web.routers.setup_status._read_env") as mock_read_env:
        mock_read_env.return_value = {"LLM_KEY_TEST_PROVIDER": "sk-test-key"}
        r = client.get("/api/setup-status")
        assert r.status_code == 200
        assert r.json()["llm_configured"] is True


def test_setup_status_resume_parsed_when_profile_has_data(client, db_session):
    """resume_parsed should be True when profile has structured data."""
    # Create a profile with skills
    profile_data = {
        "first_name": "John",
        "last_name": "Doe",
        "skills": ["Python", "JavaScript"],
        "work_history": [],
        "education": [],
        "projects": [],
    }
    user = User(name="Test User", data=json.dumps(profile_data))
    db_session.add(user)
    db_session.commit()

    # Set as active profile
    db_session.add(Config(key="active_profile_id", value=str(user.id)))
    db_session.commit()

    r = client.get("/api/setup-status")
    assert r.status_code == 200
    assert r.json()["resume_parsed"] is True


def test_setup_status_resume_not_parsed_when_profile_has_no_data(client, db_session):
    """resume_parsed should be False when profile has no structured data."""
    # Create an empty profile
    profile_data = {
        "first_name": "",
        "last_name": "",
        "skills": [],
        "work_history": [],
        "education": [],
        "projects": [],
    }
    user = User(name="Empty User", data=json.dumps(profile_data))
    db_session.add(user)
    db_session.commit()

    # Set as active profile
    db_session.add(Config(key="active_profile_id", value=str(user.id)))
    db_session.commit()

    r = client.get("/api/setup-status")
    assert r.status_code == 200
    assert r.json()["resume_parsed"] is False
