"""Tests for tree-v1 resume user-feedback refine path."""
import json
from contextlib import contextmanager
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import Base, Document, PromptDefault
from core.job import Job, JobState
import core.user  # noqa: F401 — ensure User model registered
import web.intake_pipeline as ip
from web.intake_pipeline import build_feedback_issues


# ---------------------------------------------------------------------------
# Unit tests for build_feedback_issues
# ---------------------------------------------------------------------------

def test_build_feedback_issues_carries_section():
    notes = [{"node_id": "f1", "section": "Summary", "label": "Summary", "note": "punchier"}]
    issues = build_feedback_issues(notes)
    assert issues == [{"category": "user_feedback",
                       "description": "Summary: punchier", "section": "Summary"}]


def test_build_feedback_issues_drops_blank():
    assert build_feedback_issues([{"section": "X", "label": "X", "note": "  "}]) == []


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

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


@pytest.fixture
def tree_v1_job(db_session, monkeypatch, tmp_path):
    """Seed a User with profile tree, a Job, and a tree-v1 Document row."""
    from core.user import User as UserEntity
    from core.document_tree import build_resume_document_tree
    from core.resume_document_io import serialize_document_tree

    data = {
        "first_name": "Jane", "last_name": "Doe", "email": "j@x.co",
        "hero": "old", "skills": ["py"],
    }
    db_session.add(UserEntity(name="Jane Doe", data=json.dumps(data)))
    db_session.commit()
    user = UserEntity.load(db_session)
    root = user.profile_tree_root()
    tree = build_resume_document_tree(root, {})
    job = Job(job_key="fb1", title="t", company="c", source="x",
              url="u/fb1", state=JobState.NEW.value, profile_id=1)
    db_session.add(job)
    db_session.commit()
    Document.upsert(db_session, "fb1", "resume", serialize_document_tree(tree), profile_id=1)

    # Seed prompt defaults
    db_session.add(PromptDefault(type_key="resume_eval_sectioned",
                                 content="dummy eval prompt with enough words to pass the minimum"))
    db_session.add(PromptDefault(type_key="resume",
                                 content="dummy resume prompt with enough words to pass the minimum"))
    db_session.commit()

    # Monkeypatch infrastructure
    monkeypatch.setattr(ip, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)
    monkeypatch.setattr(ip, "_emit", lambda j: None)
    monkeypatch.setattr(ip, "llm_status", MagicMock())
    monkeypatch.setattr(ip, "get_client_for_profile", lambda u, m="": (object(), "m"))
    monkeypatch.setattr(Job, "generate_resume_pdf", lambda self, *a, **k: None)
    monkeypatch.setattr(Job, "build_resume_prompt", lambda self, u, t, db: "prompt")

    @contextmanager
    def fake_meter(*a, **kw):
        yield

    monkeypatch.setattr(ip, "meter_action", fake_meter)
    monkeypatch.setattr(ip, "_OUTPUTS_DIR", tmp_path)
    import core.job as _cj
    monkeypatch.setattr(_cj, "_OUTPUTS_DIR", tmp_path)

    # Write a dummy .md so write_resume_markdown target dir exists
    (tmp_path / "fb1_resume.md").write_text("dummy", encoding="utf-8")

    return "fb1"


# ---------------------------------------------------------------------------
# Engine test
# ---------------------------------------------------------------------------

def test_feedback_refine_regenerates_only_commented_section(tree_v1_job, db_session):
    from web.intake_pipeline import _run_resume_feedback_refine
    notes = [{"node_id": "f1", "section": "Summary", "label": "Summary", "note": "punchier"}]
    captured = {}

    def fake_gen(root, ctx, client, model, resolve=None, only_sections=None, critiques=None):
        captured["only"] = set(only_sections or set())
        captured["crit"] = critiques or {}
        return {}  # no field changes; carry-forward keeps prior values

    with patch("web.intake_pipeline.generate_resume_by_section", side_effect=fake_gen), \
         patch("web.intake_pipeline.run_ats_gate"):
        _run_resume_feedback_refine(tree_v1_job, "resume", notes, profile_id=1)

    assert captured["only"] == {"Summary"}
    assert "Summary" in captured["crit"]
    assert captured["crit"]["Summary"][0]["description"] == "Summary: punchier"


# ---------------------------------------------------------------------------
# Metering: a hard failure in the tree-v1 refine must refund the regenerate debit
# ---------------------------------------------------------------------------

def test_tree_v1_refine_hard_fail_refunds_and_marks_errored(
        tree_v1_job, db_session, monkeypatch):
    """A metered account: the 2u regenerate debit is refunded (balance restored)
    and the job is marked errored when the selective-regen LLM step blows up."""
    from db.database import Account, CreditLedger
    from core.metering import meter_action as real_meter

    # Restore the real meter (the fixture stubbed it to a no-op) so the ledger
    # records the debit + refund.
    monkeypatch.setattr(ip, "meter_action", real_meter)

    db_session.add(Account(
        id=1, email="acct@example.com", profile_id=1,
        created_at="2026-01-01T00:00:00+00:00",
        credit_balance=5, credit_rate=1.5,
    ))
    db_session.commit()

    def boom(*a, **k):
        raise RuntimeError("selective regen exploded")

    notes = [{"node_id": "f1", "section": "Summary", "label": "Summary", "note": "punchier"}]
    with patch("web.intake_pipeline.generate_resume_by_section", side_effect=boom), \
         patch("web.intake_pipeline.run_ats_gate"):
        # Must not crash the (background) worker despite the hard failure.
        ip.run_user_feedback_refine("fb1", "resume", notes, profile_id=1)

    # Ledger: exactly one debit (-2) and one matching refund (+2).
    rows = db_session.query(CreditLedger).order_by(CreditLedger.id).all()
    debits = [r for r in rows if r.reason == "debit"]
    refunds = [r for r in rows if r.reason == "refund"]
    assert len(debits) == 1 and debits[0].delta == -2 and debits[0].action == "regenerate"
    assert len(refunds) == 1 and refunds[0].delta == 2 and refunds[0].action == "regenerate"

    # Balance restored to the starting value.
    bal = db_session.query(Account).filter_by(profile_id=1).first().credit_balance
    assert bal == 5

    # Job marked errored by the delegate before re-raising.
    job = Job.get("fb1", db_session, 1)
    assert job.unread_indicator == "error"
    assert "feedback refine failed" in (job.last_result_error or "").lower()
