"""Regression tests for profile prompt-status endpoints."""
import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import get_db, Base, Config, Prompt
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


_LONG_CONTENT = " ".join(["word"] * 20)   # 20 words — above the >10 threshold
_SHORT_CONTENT = "too short"              # 2 words — at or below threshold

_ALL_PROMPT_TYPES = ("scoring", "resume", "cover", "extraction", "resume_parse")


# ---- helpers ----

def _seed_profile(db_session, name="Test User") -> int:
    row = User(name=name, data=json.dumps({"first_name": "X"}))
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row.id


def _set_active_profile(db_session, profile_id: int) -> None:
    db_session.add(Config(key="active_profile_id", value=str(profile_id)))
    db_session.commit()


def _seed_prompt(db_session, profile_id: int, type_key: str, content: str, model: str = "") -> None:
    db_session.add(Prompt(profile_id=profile_id, type_key=type_key, content=content, model=model))
    db_session.commit()


# ---- Test 1: active profile with one configured prompt ----

def test_prompt_status_configured_type_true_others_false(client, db_session):
    profile_id = _seed_profile(db_session)
    _set_active_profile(db_session, profile_id)
    _seed_prompt(db_session, profile_id, "scoring", _LONG_CONTENT)

    resp = client.get("/api/config/profiles/active/prompt-status")
    assert resp.status_code == 200
    data = resp.json()

    assert data["scoring"] is True
    for t in _ALL_PROMPT_TYPES:
        if t != "scoring":
            assert data[t] is False, f"Expected {t} to be False"


# ---- Test 2: short content counts as not configured ----

def test_prompt_status_short_content_is_false(client, db_session):
    profile_id = _seed_profile(db_session)
    _set_active_profile(db_session, profile_id)
    _seed_prompt(db_session, profile_id, "resume", _SHORT_CONTENT)

    resp = client.get("/api/config/profiles/active/prompt-status")
    assert resp.status_code == 200
    assert resp.json()["resume"] is False


# ---- Test 3: no profiles → all False ----

def test_prompt_status_no_profiles_all_false(client, db_session):
    # No profiles seeded, no active_profile_id set
    resp = client.get("/api/config/profiles/active/prompt-status")
    assert resp.status_code == 200
    data = resp.json()
    for t in _ALL_PROMPT_TYPES:
        assert data[t] is False, f"Expected {t} to be False when no profiles exist"


# ---- Test 4: GET /api/config/profiles/{profile_id} with seeded Prompt ----

def test_get_profile_prompt_fields(client, db_session, tmp_path, monkeypatch):
    import web.routers.config as config_mod
    monkeypatch.setattr(config_mod, "_ENV_PATH", tmp_path / ".env")

    profile_id = _seed_profile(db_session)
    _seed_prompt(db_session, profile_id, "scoring", _LONG_CONTENT, model="gpt-x")

    resp = client.get(f"/api/config/profiles/{profile_id}")
    assert resp.status_code == 200
    data = resp.json()

    assert data["prompt_scoring_model"] == "gpt-x"
    assert data["prompt_scoring_configured"] is True
    assert "prompt_scoring_file" not in data
