"""Tests for onboarding tour state persistence + endpoints."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from web.main import app
from web.tenancy import current_profile_id
from core.user import User
from db.database import get_db, Base


@pytest.fixture
def db_session():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    s = sessionmaker(bind=eng)()
    yield s
    s.close()


@pytest.fixture
def seeded_profile(db_session):
    user = User(id=1, name="Test User", data="{}")
    db_session.add(user)
    db_session.commit()
    return user


def _client(db_session, profile_id):
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[current_profile_id] = lambda: profile_id
    return TestClient(app)


def test_default_state_is_unstarted(db_session, seeded_profile):
    client = _client(db_session, seeded_profile.id)
    body = client.get("/api/setup-status").json()
    assert body["onboarding_tour"] == "unstarted"
    app.dependency_overrides.clear()


def test_patch_advances_state_and_persists(db_session, seeded_profile):
    client = _client(db_session, seeded_profile.id)
    r = client.patch("/api/onboarding/tour", json={"state": "part1_done"})
    assert r.status_code == 200
    assert r.json()["onboarding_tour"] == "part1_done"
    # reload from DB to confirm persistence
    reloaded = User.load(db_session, seeded_profile.id)
    assert reloaded.onboarding_tour == "part1_done"
    app.dependency_overrides.clear()


def test_patch_rejects_unknown_state(db_session, seeded_profile):
    client = _client(db_session, seeded_profile.id)
    r = client.patch("/api/onboarding/tour", json={"state": "banana"})
    assert r.status_code == 422
    app.dependency_overrides.clear()


def test_patch_rejects_downgrade_from_terminal(db_session, seeded_profile):
    client = _client(db_session, seeded_profile.id)
    client.patch("/api/onboarding/tour", json={"state": "completed"})
    r = client.patch("/api/onboarding/tour", json={"state": "part1_done"})
    assert r.status_code == 409
    app.dependency_overrides.clear()
