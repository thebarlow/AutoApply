"""Tests for the per-section tree-v1 resume refinement orchestrator."""
import json
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import Base, Document, PromptDefault
from core.job import Job, JobState
import core.user  # noqa: F401 — ensure User model registered
import web.intake_pipeline as ip


@pytest.fixture
def db_session():
    import core.job   # noqa: F401
    import core.user  # noqa: F401
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


def test_only_failing_section_regenerated_and_stops_when_all_pass(db_session, monkeypatch, tmp_path):
    """Only sub-threshold sections are regenerated; loop stops when all pass; row stays tree-v1."""
    from core.user import User as UserEntity
    from core.document_tree import build_resume_document_tree
    from core.resume_document_io import serialize_document_tree, is_tree_v1

    # --- seed profile + job + tree-v1 resume ---
    data = {
        "first_name": "Jane", "last_name": "Doe", "email": "j@x.co",
        "hero": "old", "skills": ["py"],
    }
    db_session.add(UserEntity(name="Jane Doe", data=json.dumps(data)))
    db_session.commit()
    user = UserEntity.load(db_session)
    root = user.profile_tree_root()
    tree = build_resume_document_tree(root, {})
    job = Job(job_key="sr1", title="t", company="c", source="x",
              url="u/sr1", state=JobState.NEW.value, profile_id=1)
    db_session.add(job)
    db_session.commit()
    Document.upsert(db_session, "sr1", "resume", serialize_document_tree(tree), profile_id=1)

    # Seed prompt defaults so resolve_prompt succeeds
    db_session.add(PromptDefault(type_key="resume_eval_sectioned",
                                 content="dummy eval prompt with enough words to pass the minimum"))
    db_session.add(PromptDefault(type_key="resume",
                                 content="dummy resume prompt with enough words to pass the minimum"))
    db_session.commit()

    # --- monkeypatch SessionLocal to return our test session ---
    monkeypatch.setattr(ip, "SessionLocal", lambda: db_session)
    # Prevent db.close() from actually closing our shared session
    monkeypatch.setattr(db_session, "close", lambda: None)

    # --- eval stub: Summary fails turn 1, passes turn 2; Skills always passes ---
    calls = {"n": 0}

    def fake_eval(self, eval_prompt, user, client, model, db):
        calls["n"] += 1
        summ = 0.4 if calls["n"] == 1 else 0.95
        return {
            "Summary": {"score": summ, "issues": [{"category": "tailoring", "description": "g"}]},
            "Skills": {"score": 0.95, "issues": []},
        }

    monkeypatch.setattr(Job, "evaluate_resume_sections", fake_eval)

    # --- regen stub: record only_sections, return empty (no field changes) ---
    regen_sections = []

    def fake_regen(root, job_ctx, client, model, resolve=None, only_sections=None, critiques=None):
        regen_sections.append(set(only_sections or set()))
        return {}

    monkeypatch.setattr(ip, "generate_resume_by_section", fake_regen)

    # --- stub PDF generation (avoid Chromium) ---
    monkeypatch.setattr(Job, "generate_resume_pdf", lambda self, *a, **k: None)

    # --- stub LLM client ---
    monkeypatch.setattr(ip, "get_client_for_profile", lambda u, m="": (object(), "m"))

    # --- stub SSE + llm_status ---
    monkeypatch.setattr(ip, "_emit", lambda j: None)
    monkeypatch.setattr(ip, "llm_status", MagicMock())

    # --- stub meter_action as a no-op context manager ---
    from contextlib import contextmanager

    @contextmanager
    def fake_meter(*a, **kw):
        yield

    monkeypatch.setattr(ip, "meter_action", fake_meter)

    # --- stub outputs dir to tmp_path ---
    monkeypatch.setattr(Job, "build_resume_prompt", lambda self, u, t, db: "prompt")

    # --- run ---
    ip._run_resume_section_refinement("sr1", 1)

    # --- assertions ---
    assert regen_sections == [{"Summary"}], f"Expected only Summary regenerated, got {regen_sections}"
    row = Document.fetch(db_session, "sr1", "resume", profile_id=1)
    assert is_tree_v1(row.structured_json), "Document should remain tree-v1"
