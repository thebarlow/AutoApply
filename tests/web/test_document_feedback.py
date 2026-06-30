import pytest

from web.intake_pipeline import build_feedback_issues


def test_build_feedback_issues_formats_and_filters():
    notes = [
        {"section": "summary", "label": "Profile summary", "note": "make punchier"},
        {"section": "experience:0", "label": "Experience [0] (Eng at Acme)", "note": "  quantify  "},
        {"section": "skills", "label": "Skills", "note": "   "},   # dropped (empty)
    ]
    issues = build_feedback_issues(notes)
    assert issues == [
        {"category": "user_feedback", "description": "Profile summary: make punchier", "section": "summary"},
        {"category": "user_feedback", "description": "Experience [0] (Eng at Acme): quantify", "section": "experience:0"},
    ]


def test_build_feedback_issues_empty():
    assert build_feedback_issues([]) == []
    assert build_feedback_issues([{"label": "x", "note": ""}]) == []


import json
from unittest.mock import MagicMock, patch


def test_run_user_feedback_refine_keeps_user_version():
    """Applies refine with built issues, appends a user_feedback eval turn,
    sets the score, and never restores a prior 'best' turn.

    Exercised via the cover path: covers use the generic refine loop in
    run_user_feedback_refine (résumés route to the tree-only
    _run_resume_feedback_refine instead).
    """
    notes = [{"section": "body", "label": "Body", "note": "punchier"}]

    job = MagicMock()
    job.cover_eval_log = json.dumps([
        {"turn": 1, "score": 0.95, "issues": [], "passed": True},  # a higher prior turn
    ])
    refine_fn = MagicMock()
    job.refine_cover_md = refine_fn
    job.evaluate_cover_md = MagicMock(return_value={"score": 0.50, "issues": [{"category": "x", "description": "y"}]})

    user = MagicMock()
    user.resolve_prompt.return_value = "PROMPT"
    user.cover_refine_pass_score = 0.80

    import web.intake_pipeline as ip
    with patch.object(ip, "SessionLocal") as SL, \
         patch.object(ip.Job, "get", return_value=job), \
         patch.object(ip.User, "load", return_value=user), \
         patch.object(ip, "get_client_for_profile", return_value=("client", "model")), \
         patch("core.metering.get_account_for_profile", return_value=None), \
         patch.object(ip, "_emit"):
        SL.return_value = MagicMock()
        ip.run_user_feedback_refine("k1", "cover", notes, 1)

    # refine called with our built issues
    args, kwargs = refine_fn.call_args
    passed_issues = args[5]  # (user, prompt, client, model, db, issues, template)
    assert passed_issues == [{"category": "user_feedback", "description": "Body: punchier", "section": "body"}]

    # a user_feedback turn was appended with the new (lower) score; no restore to 0.95
    log = json.loads(job.cover_eval_log)
    assert log[-1]["source"] == "user_feedback"
    assert log[-1]["score"] == 0.50
    assert log[-1]["passed"] is False  # 0.50 < pass_score 0.80
    assert job.cover_eval_score == 0.50  # kept the user-directed result, not 0.95


from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from db.database import get_db, Base, Document
from core.job import Job, JobState
import core.user  # noqa: F401


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def client(db_session):
    from web.main import app
    from web.tenancy import current_profile_id
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[current_profile_id] = lambda: 1
    yield TestClient(app)
    app.dependency_overrides.clear()


def _job(db, key="k1"):
    j = Job(job_key=key, profile_id=1, source="x", title="t", company="Acme", url=f"u/{key}", state=JobState.NEW.value)
    db.add(j)
    db.commit()
    return j


def test_feedback_404_no_job(client):
    r = client.post("/api/jobs/missing/resume/feedback", json={"notes": []})
    assert r.status_code == 404


def test_feedback_404_no_document(client, db_session, tmp_path, monkeypatch):
    # No row and no on-disk .md to backfill from → nothing to refine.
    import web.routers.jobs as jobs_mod
    monkeypatch.setattr(jobs_mod, "_OUTPUTS_DIR", tmp_path, raising=False)
    _job(db_session)
    r = client.post("/api/jobs/k1/resume/feedback",
                    json={"notes": [{"section": "summary", "label": "Profile summary", "note": "punchier"}]})
    assert r.status_code == 404


def test_feedback_backfills_row_from_markdown(client, db_session, tmp_path, monkeypatch):
    """A job that was only viewed (no row) but has an on-disk .md should have a row
    backfilled+persisted so the spawned refine has a structured base to patch."""
    import web.routers.jobs as jobs_mod
    monkeypatch.setattr(jobs_mod, "_OUTPUTS_DIR", tmp_path, raising=False)
    calls = []
    monkeypatch.setattr(jobs_mod, "_spawn", lambda *a: calls.append(a))
    (tmp_path / "k1_resume.md").write_text(
        "---\nname: Jane Doe\n---\n## Profile\n\nEngineer who ships.\n", encoding="utf-8",
    )
    _job(db_session)
    assert Document.fetch(db_session, "k1", "resume", profile_id=1) is None

    r = client.post("/api/jobs/k1/resume/feedback",
                    json={"notes": [{"section": "summary", "label": "Profile summary", "note": "punchier"}]})
    assert r.status_code == 202
    # Row was persisted and the refine was spawned.
    assert Document.fetch(db_session, "k1", "resume", profile_id=1) is not None
    assert calls and calls[0][1] == "k1" and calls[0][2] == "resume"


def test_feedback_400_empty_notes(client, db_session):
    _job(db_session)
    Document.upsert(db_session, "k1", "resume", '{"profile_summary":"x"}', profile_id=1)
    r = client.post("/api/jobs/k1/resume/feedback", json={"notes": [{"label": "x", "note": "  "}]})
    assert r.status_code == 400


def test_feedback_202_spawns(client, db_session, monkeypatch):
    from web.routers import jobs as jobs_router
    calls = []
    monkeypatch.setattr(jobs_router, "_spawn", lambda *a: calls.append(a))
    _job(db_session)
    Document.upsert(db_session, "k1", "resume", '{"profile_summary":"x"}', profile_id=1)
    r = client.post("/api/jobs/k1/resume/feedback",
                    json={"notes": [{"section": "summary", "label": "Profile summary", "note": "punchier"}]})
    assert r.status_code == 202
    assert calls and calls[0][1] == "k1" and calls[0][2] == "resume"
    assert calls[0][3] == [{"section": "summary", "label": "Profile summary", "note": "punchier"}]
