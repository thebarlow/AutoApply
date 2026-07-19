"""Tests for per-slot DB-backed prompt endpoints."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import get_db, Base, Prompt, PromptDefault
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

    # Seed: a User profile
    user = User(id=1, name="Test User")
    session.add(user)

    # Seed: a PromptDefault for "scoring"
    session.add(PromptDefault(type_key="scoring", content="default scoring " * 10))

    # Seed: a Prompt row for profile 1 / scoring
    session.add(Prompt(
        profile_id=1,
        type_key="scoring",
        content="body " * 10,
        model="",
        updated_at="t",
    ))

    session.commit()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


# ---- GET slot ----

def test_get_prompt_returns_200_with_expected_keys(client):
    resp = client.get("/api/prompts/1/scoring")
    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == {"content", "model", "is_default"}


def test_get_prompt_unknown_type_returns_404(client):
    resp = client.get("/api/prompts/1/bogus")
    assert resp.status_code == 404


def test_get_prompt_no_row_returns_default(client, db_session):
    # "resume" has a default but no Prompt row for profile 1
    db_session.add(PromptDefault(type_key="resume", content="default resume " * 10))
    db_session.commit()

    resp = client.get("/api/prompts/1/resume")
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_default"] is True
    assert "default resume" in data["content"]


# ---- PUT slot ----

def test_put_prompt_persists_and_get_returns_new_content(client):
    resp = client.put("/api/prompts/1/scoring", json={"content": "new content " * 10, "model": "m"})
    assert resp.status_code == 200

    get_resp = client.get("/api/prompts/1/scoring")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert "new content" in data["content"]
    assert data["model"] == "m"


def test_put_blank_content_returns_400(client):
    resp = client.put("/api/prompts/1/scoring", json={"content": "   ", "model": ""})
    assert resp.status_code == 400


# ---- POST reset ----

def test_reset_returns_default(client):
    # First PUT to override
    client.put("/api/prompts/1/scoring", json={"content": "overridden content " * 10, "model": ""})
    # Then reset
    resp = client.post("/api/prompts/1/scoring/reset")
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_default"] is True
    assert "default scoring" in data["content"]


# ---- Removed endpoint ----

def test_old_list_endpoint_not_json_api(client):
    # The old GET /api/prompts list endpoint is removed.
    # The SPA catch-all may return 200 with HTML, but it must NOT return
    # the old {"prompts": [...]} JSON shape.
    # A 200 here means the frontend catch-all route returned the SPA shell HTML, not a JSON API response.
    resp = client.get("/api/prompts")
    if resp.status_code == 200:
        ct = resp.headers.get("content-type", "")
        assert "application/json" not in ct, "Old list endpoint is still returning JSON"
    else:
        assert resp.status_code == 404


# ---- Unknown profile ----

def test_unknown_profile_404(client):
    assert client.get("/api/prompts/999/scoring").status_code == 404
    assert client.put("/api/prompts/999/scoring", json={"content": "x " * 20, "model": ""}).status_code == 404


# ---- Reset clears model ----

def test_reset_clears_model(client):
    # PUT with a non-empty model override
    client.put("/api/prompts/1/scoring", json={"content": "overridden " * 10, "model": "m"})
    # Reset should restore default and clear the model
    client.post("/api/prompts/1/scoring/reset")
    data = client.get("/api/prompts/1/scoring").json()
    assert data["model"] == ""
    assert data["is_default"] is True


# ---- Defaults endpoint ----

def test_get_default_prompt_returns_200_with_content(client):
    resp = client.get("/api/prompts/defaults/scoring")
    assert resp.status_code == 200
    data = resp.json()
    assert "content" in data
    assert "default scoring" in data["content"]


# ---- Model allowlist ----

def test_put_prompt_rejects_disallowed_model(client, monkeypatch):
    monkeypatch.setenv("LLM_ALLOWED_MODELS", "openai/gpt-4o-mini")
    resp = client.put(
        "/api/prompts/1/scoring",
        json={"content": "overridden " * 10, "model": "openai/o1-pro"},
    )
    assert resp.status_code == 422


def test_put_prompt_accepts_allowed_model(client, monkeypatch):
    monkeypatch.setenv("LLM_ALLOWED_MODELS", "openai/gpt-4o-mini")
    resp = client.put(
        "/api/prompts/1/scoring",
        json={"content": "overridden " * 10, "model": "openai/gpt-4o-mini"},
    )
    assert resp.status_code == 200
    assert resp.json()["model"] == "openai/gpt-4o-mini"


def test_put_prompt_empty_model_always_allowed(client, monkeypatch):
    monkeypatch.setenv("LLM_ALLOWED_MODELS", "openai/gpt-4o-mini")
    resp = client.put(
        "/api/prompts/1/scoring",
        json={"content": "overridden " * 10, "model": ""},
    )
    assert resp.status_code == 200
