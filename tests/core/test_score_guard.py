"""score() refuses to run on a blank-description (failed-scrape) job."""
import pytest

from core.job import Job


def _blank_job():
    j = Job.__new__(Job)
    j.description = ""
    j.job_key = "indeed_blank"
    j.desirability_score = None
    j.fit_score = None
    j.final_score = None
    j.score_justification = None
    return j


def test_score_refuses_empty_description():
    job = _blank_job()
    # client/user/etc. are irrelevant — the guard must fire before they're touched.
    with pytest.raises(RuntimeError, match="empty description"):
        job.score(user=None, config={}, client=None, model="x", db=None,
                  prompt_content="")
    assert job.final_score is None
