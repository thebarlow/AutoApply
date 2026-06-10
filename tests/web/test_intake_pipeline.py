from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import get_db, Base
from core.job import Job, JobState
import core.user  # noqa: F401
from web.intake_pipeline import run_pipeline


@pytest.fixture
def db_session():
    import core.job   # noqa: F401
    import core.user  # noqa: F401
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


def _make_db_job(job_key="abc123"):
    job = MagicMock()
    job.job_key = job_key
    return job


def test_run_pipeline_calls_extraction_then_scoring(monkeypatch):
    """Both steps run in order on success."""
    calls = []

    mock_job = _make_db_job()
    mock_db = MagicMock()

    with patch("web.intake_pipeline.SessionLocal", return_value=mock_db), \
         patch("web.intake_pipeline.Job") as MockJob, \
         patch("web.intake_pipeline._do_extract_description", side_effect=lambda j, db: calls.append("extract")), \
         patch("web.intake_pipeline._do_score", side_effect=lambda j, db: calls.append("score")), \
         patch("web.intake_pipeline.llm_status"), \
         patch("web.intake_pipeline._emit"):

        MockJob.get.return_value = mock_job
        run_pipeline("abc123")

    assert calls == ["extract", "score"]


def test_run_pipeline_skips_scoring_if_extraction_fails(monkeypatch):
    """Scoring is skipped when extraction raises."""
    calls = []

    mock_job = _make_db_job()
    mock_db = MagicMock()

    with patch("web.intake_pipeline.SessionLocal", return_value=mock_db), \
         patch("web.intake_pipeline.Job") as MockJob, \
         patch("web.intake_pipeline._do_extract_description", side_effect=RuntimeError("boom")), \
         patch("web.intake_pipeline._do_score", side_effect=lambda j, db: calls.append("score")), \
         patch("web.intake_pipeline.llm_status"), \
         patch("web.intake_pipeline._emit"):

        MockJob.get.return_value = mock_job
        run_pipeline("abc123")

    assert calls == []


def test_run_pipeline_closes_db_session_on_error(monkeypatch):
    """DB session is always closed."""
    mock_db = MagicMock()

    with patch("web.intake_pipeline.SessionLocal", return_value=mock_db), \
         patch("web.intake_pipeline.Job") as MockJob, \
         patch("web.intake_pipeline._do_extract_description", side_effect=RuntimeError("fail")), \
         patch("web.intake_pipeline._do_score"), \
         patch("web.intake_pipeline.llm_status"), \
         patch("web.intake_pipeline._emit"):

        MockJob.get.return_value = _make_db_job()
        run_pipeline("abc123")

    mock_db.close.assert_called_once()


def test_turn_snapshot_is_structured_json(tmp_path, monkeypatch):
    # Pydantic round-trip format smoke test only: confirms a snapshot written as
    # ResumeDocument JSON re-validates cleanly. Does not exercise any route or pipeline.
    import web.intake_pipeline as ip
    from core.schemas import ResumeDocument, ResumeExperience
    from db.database import Document
    job_key = "snap1"
    doc = ResumeDocument(experience=[ResumeExperience(company="Acme", title="Eng", description="x")])
    snap = tmp_path / f"{job_key}_resume_turn_0.json"
    snap.write_text(doc.model_dump_json(), encoding="utf-8")
    loaded = ResumeDocument.model_validate_json(snap.read_text(encoding="utf-8"))
    assert loaded.experience[0].company == "Acme"


def test_serve_doc_turn_markdown_route(client, db_session, tmp_path, monkeypatch):
    """Route assembles markdown from a turn snapshot; missing turn → 404."""
    import web.routers.jobs as jobs_router
    from core.schemas import ResumeDocument, ResumeExperience
    monkeypatch.setattr(jobs_router, "_GENERATOR_OUTPUTS", tmp_path)

    job = Job(job_key="rt1", profile_id=1, source="x", title="t", company="Acme",
              url="u/rt1", state=JobState.NEW.value)
    db_session.add(job)
    db_session.commit()

    doc = ResumeDocument(experience=[
        ResumeExperience(company="Acme", title="Staff Engineer", description="- Built widgets")
    ])
    (tmp_path / "rt1_resume_turn_0.json").write_text(doc.model_dump_json(), encoding="utf-8")

    r = client.get("/api/jobs/rt1/resume/turn/0/markdown")
    assert r.status_code == 200
    assert "Staff Engineer" in r.text

    assert client.get("/api/jobs/rt1/resume/turn/9/markdown").status_code == 404
