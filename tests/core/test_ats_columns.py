from scraper.base import ScrapedJob
from core.job import Job


def test_from_scraped_carries_apply_fields():
    sj = ScrapedJob(
        source="linkedin", job_key="k1", title="T", company="C",
        url="https://x/1", description="d", easy_apply=False,
        apply_url_raw="https://apply/1",
    )
    job = Job.from_scraped(sj)
    assert job.easy_apply is False
    assert job.apply_url_raw == "https://apply/1"


def test_serialize_exposes_ats_fields():
    job = Job.from_scraped(ScrapedJob(
        source="linkedin", job_key="k2", title="T", company="C",
        url="https://x/2", description="d",
    ))
    job.ats_type = "greenhouse"
    job.ats_domain = "boards.greenhouse.io"
    data = job.serialize()
    for key in ("easy_apply", "apply_url_raw", "apply_url_resolved", "ats_type", "ats_domain"):
        assert key in data
    assert data["ats_type"] == "greenhouse"
