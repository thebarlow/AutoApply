from unittest.mock import patch, MagicMock
import pytest

from web.intake_pipeline import run_pipeline


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
    import web.intake_pipeline as ip
    from core.schemas import ResumeDocument, ResumeExperience
    from db.database import Document
    job_key = "snap1"
    doc = ResumeDocument(experience=[ResumeExperience(company="Acme", title="Eng", description="x")])
    snap = tmp_path / f"{job_key}_resume_turn_0.json"
    snap.write_text(doc.model_dump_json(), encoding="utf-8")
    loaded = ResumeDocument.model_validate_json(snap.read_text(encoding="utf-8"))
    assert loaded.experience[0].company == "Acme"
