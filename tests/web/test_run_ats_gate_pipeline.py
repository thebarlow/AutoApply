from __future__ import annotations

from unittest.mock import MagicMock, patch

from core.schemas import AtsReport


def test_run_ats_gate_stores_report_and_emits():
    """run_ats_gate resolves client, runs the check, persists, and emits."""
    import web.intake_pipeline as pipeline

    job = MagicMock()
    report = AtsReport.build(score=1.0, issues=[], extracted_text="t")
    job.run_ats_check.return_value = report

    fake_db = MagicMock()
    with patch.object(pipeline, "SessionLocal", return_value=fake_db), \
         patch.object(pipeline.Job, "get", return_value=job), \
         patch.object(pipeline.User, "load", return_value=object()), \
         patch.object(pipeline, "get_client_for_profile", return_value=(object(), "m")), \
         patch.object(pipeline, "_emit") as emit:
        pipeline.run_ats_gate("job1", 1)

    job.run_ats_check.assert_called_once()
    job.store_ats_report.assert_called_once_with(report)
    fake_db.commit.assert_called()
    emit.assert_called_once()


def test_run_ats_gate_swallows_missing_artifact():
    """A missing PDF/Document must not raise out of the background thread."""
    import web.intake_pipeline as pipeline

    job = MagicMock()
    job.run_ats_check.side_effect = FileNotFoundError("no pdf")

    fake_db = MagicMock()
    with patch.object(pipeline, "SessionLocal", return_value=fake_db), \
         patch.object(pipeline.Job, "get", return_value=job), \
         patch.object(pipeline.User, "load", return_value=object()), \
         patch.object(pipeline, "get_client_for_profile", return_value=(object(), "m")), \
         patch.object(pipeline, "_emit"):
        pipeline.run_ats_gate("job1", 1)  # must not raise

    job.store_ats_report.assert_not_called()


def test_run_ats_gate_skips_on_insufficient_credits():
    """A zero-balance tenant must not get a free ATS LLM run."""
    import web.intake_pipeline as pipeline
    from contextlib import contextmanager
    from core.credits import InsufficientCredits

    job = MagicMock()

    @contextmanager
    def broke_meter(db, profile_id, **kw):
        raise InsufficientCredits(0, 10)
        yield

    fake_db = MagicMock()
    with patch.object(pipeline, "SessionLocal", return_value=fake_db), \
         patch.object(pipeline.Job, "get", return_value=job), \
         patch.object(pipeline.User, "load", return_value=object()), \
         patch.object(pipeline, "get_client_for_profile", return_value=(object(), "m")), \
         patch.object(pipeline, "meter_action", broke_meter), \
         patch.object(pipeline, "_emit"):
        pipeline.run_ats_gate("job1", 1, metered=True)  # must not raise

    job.run_ats_check.assert_not_called()
    job.store_ats_report.assert_not_called()


def test_run_resume_refinement_runs_gate_after_refine():
    """The résumé post-process runs the gate after refinement settles."""
    import web.intake_pipeline as pipeline

    calls = []
    with patch.object(pipeline, "_run_doc_refinement", side_effect=lambda k, d, p: calls.append(("refine", k, d))), \
         patch.object(pipeline, "run_ats_gate", side_effect=lambda k, p: calls.append(("gate", k))):
        pipeline.run_resume_refinement("job1", 1)

    assert calls == [("refine", "job1", "resume"), ("gate", "job1")]
