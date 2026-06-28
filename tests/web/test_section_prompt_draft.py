"""Tests for POST /api/config/section-prompt/draft (Task 6).

Monkeypatches the LLM call so no real model runs.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import get_db, Base, PromptDefault
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


@pytest.fixture
def seeded_client(client, db_session):
    """Client whose DB already has a profile row + the section_prompt_assist seed."""
    # Create a profile so current_profile_id (→ 1 in dev-stub) resolves.
    client.post("/api/config/profiles", json={"name": "Test User"})
    # Seed the prompt default the endpoint reads.
    db_session.add(
        PromptDefault(
            type_key="section_prompt_assist",
            content=(
                "You write a résumé section instruction.\n\n"
                "Output ONLY raw JSON: {\"prompt\": \"<instruction>\"}\n\n"
                "Section: {section_name}\nPurpose: {purpose}\nPer-job tailoring: {tailoring}"
            ),
        )
    )
    db_session.commit()
    return client


def test_draft_section_prompt(seeded_client, monkeypatch):
    """Returns 200 + non-empty prompt when LLM call is mocked."""
    import web.routers.config as cfg

    monkeypatch.setattr(
        cfg,
        "_llm_json_with_retry",
        lambda *a, **k: cfg.SectionPromptDraft(prompt="Reorder certs by relevance."),
    )
    monkeypatch.setattr(
        cfg,
        "get_client_for_profile",
        lambda *a, **k: (object(), "mock-model"),
    )

    resp = seeded_client.post(
        "/api/config/section-prompt/draft",
        json={"section_name": "Certifications", "purpose": "creds", "tailoring": "reorder"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["prompt"] == "Reorder certs by relevance."


def test_draft_missing_seed_returns_500(client, db_session, monkeypatch):
    """When the seed row is absent, endpoint returns 500."""
    import web.routers.config as cfg

    client.post("/api/config/profiles", json={"name": "Test User"})
    monkeypatch.setattr(
        cfg,
        "get_client_for_profile",
        lambda *a, **k: (object(), "mock-model"),
    )

    resp = client.post(
        "/api/config/section-prompt/draft",
        json={"section_name": "Skills", "purpose": "tech stack", "tailoring": "match JD"},
    )
    assert resp.status_code == 500


def test_draft_llm_error_returns_502(seeded_client, monkeypatch):
    """When the LLM call raises, endpoint returns 502."""
    import web.routers.config as cfg

    monkeypatch.setattr(
        cfg,
        "get_client_for_profile",
        lambda *a, **k: (object(), "mock-model"),
    )
    monkeypatch.setattr(
        cfg,
        "_llm_json_with_retry",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("LLM timeout")),
    )

    resp = seeded_client.post(
        "/api/config/section-prompt/draft",
        json={"section_name": "Skills", "purpose": "tech stack", "tailoring": "match JD"},
    )
    assert resp.status_code == 502
