"""run_pipeline flags a blank-description job and skips extract+score."""
from unittest.mock import patch

import web.intake_pipeline as pipeline
from core.job import Job


class _FakeJob:
    def __init__(self):
        self.description = ""
        self.job_key = "indeed_blank"
        self.unread_indicator = None
        self.last_result_error = None
        self.final_score = None

    has_description = Job.has_description


def test_run_pipeline_flags_failed_scrape():
    job = _FakeJob()
    with patch.object(pipeline, "SessionLocal") as SL, \
         patch.object(pipeline.Job, "get", return_value=job), \
         patch.object(pipeline, "_emit") as emit, \
         patch.object(pipeline, "_do_extract_description") as extract, \
         patch.object(pipeline, "_do_score") as score:
        pipeline.run_pipeline("indeed_blank", profile_id=9)

    assert job.unread_indicator == "error"
    assert job.last_result_error == "Scrape failed: empty description."
    assert job.final_score is None
    extract.assert_not_called()
    score.assert_not_called()
    emit.assert_called_once_with(job)
