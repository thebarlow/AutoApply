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
        {"category": "user_feedback", "description": "Profile summary: make punchier"},
        {"category": "user_feedback", "description": "Experience [0] (Eng at Acme): quantify"},
    ]


def test_build_feedback_issues_empty():
    assert build_feedback_issues([]) == []
    assert build_feedback_issues([{"label": "x", "note": ""}]) == []


import json
from unittest.mock import MagicMock, patch


def test_run_user_feedback_refine_keeps_user_version():
    """Applies refine with built issues, appends a user_feedback eval turn,
    sets the score, and never restores a prior 'best' turn."""
    notes = [{"section": "summary", "label": "Profile summary", "note": "punchier"}]

    job = MagicMock()
    job.resume_eval_log = json.dumps([
        {"turn": 1, "score": 0.95, "issues": [], "passed": True},  # a higher prior turn
    ])
    refine_fn = MagicMock()
    job.refine_resume_md = refine_fn
    job.evaluate_resume_md = MagicMock(return_value={"score": 0.50, "issues": [{"category": "x", "description": "y"}]})

    user = MagicMock()
    user.resolve_prompt.return_value = "PROMPT"
    user.resume_refine_pass_score = 0.80

    import web.intake_pipeline as ip
    with patch.object(ip, "SessionLocal") as SL, \
         patch.object(ip.Job, "get", return_value=job), \
         patch.object(ip.User, "load", return_value=user), \
         patch.object(ip, "get_client_for_profile", return_value=("client", "model")), \
         patch.object(ip, "run_ats_gate") as ats, \
         patch.object(ip, "_emit"):
        SL.return_value = MagicMock()
        ip.run_user_feedback_refine("k1", "resume", notes)

    # refine called with our built issues
    args, kwargs = refine_fn.call_args
    passed_issues = args[5]  # (user, prompt, client, model, db, issues, template)
    assert passed_issues == [{"category": "user_feedback", "description": "Profile summary: punchier"}]

    # a user_feedback turn was appended with the new (lower) score; no restore to 0.95
    log = json.loads(job.resume_eval_log)
    assert log[-1]["source"] == "user_feedback"
    assert log[-1]["score"] == 0.50
    assert log[-1]["passed"] is False  # 0.50 < pass_score 0.80
    assert job.resume_eval_score == 0.50  # kept the user-directed result, not 0.95
    ats.assert_called_once_with("k1")


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
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def _job(db, key="k1"):
    j = Job(job_key=key, source="x", title="t", company="Acme", url=f"u/{key}", state=JobState.NEW.value)
    db.add(j)
    db.commit()
    return j


def test_feedback_404_no_job(client):
    r = client.post("/api/jobs/missing/resume/feedback", json={"notes": []})
    assert r.status_code == 404


def test_feedback_404_no_document(client, db_session):
    _job(db_session)
    r = client.post("/api/jobs/k1/resume/feedback",
                    json={"notes": [{"section": "summary", "label": "Profile summary", "note": "punchier"}]})
    assert r.status_code == 404


def test_feedback_400_empty_notes(client, db_session):
    _job(db_session)
    Document.upsert(db_session, "k1", "resume", '{"profile_summary":"x"}')
    r = client.post("/api/jobs/k1/resume/feedback", json={"notes": [{"label": "x", "note": "  "}]})
    assert r.status_code == 400


def test_feedback_202_spawns(client, db_session, monkeypatch):
    from web.routers import jobs as jobs_router
    calls = []
    monkeypatch.setattr(jobs_router, "_spawn", lambda *a: calls.append(a))
    _job(db_session)
    Document.upsert(db_session, "k1", "resume", '{"profile_summary":"x"}')
    r = client.post("/api/jobs/k1/resume/feedback",
                    json={"notes": [{"section": "summary", "label": "Profile summary", "note": "punchier"}]})
    assert r.status_code == 202
    assert calls and calls[0][1] == "k1" and calls[0][2] == "resume"
    assert calls[0][3] == [{"section": "summary", "label": "Profile summary", "note": "punchier"}]
