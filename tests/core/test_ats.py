import pytest
from core.ats import classify_ats


@pytest.mark.parametrize("url,expected_type,expected_host", [
    ("https://boards.greenhouse.io/acme/jobs/123", "greenhouse", "boards.greenhouse.io"),
    ("https://acme.greenhouse.io/jobs/123", "greenhouse", "acme.greenhouse.io"),
    ("https://jobs.lever.co/acme/abc-def", "lever", "jobs.lever.co"),
    ("https://jobs.ashbyhq.com/acme/uuid", "ashby", "jobs.ashbyhq.com"),
    ("https://acme.wd1.myworkdayjobs.com/careers/job/123", "workday", "acme.wd1.myworkdayjobs.com"),
    ("https://acme.workday.com/en-US/careers", "workday", "acme.workday.com"),
    ("https://careers-acme.icims.com/jobs/456/apply", "icims", "careers-acme.icims.com"),
    ("https://acme.taleo.net/careersection/2/jobapply.ftl", "taleo", "acme.taleo.net"),
    ("https://jobs.smartrecruiters.com/Acme/12345", "smartrecruiters", "jobs.smartrecruiters.com"),
    ("https://jobs.jobvite.com/acme/job/xyz", "jobvite", "jobs.jobvite.com"),
    ("https://acme.bamboohr.com/careers/42", "bamboohr", "acme.bamboohr.com"),
    ("https://careers.acmecorp.com/apply/9", "other", "careers.acmecorp.com"),
    ("HTTPS://Jobs.Lever.CO/acme/x", "lever", "jobs.lever.co"),  # case-insensitive host
    ("", "other", ""),
    ("not a url", "other", ""),
    ("javascript:void(0)", "other", ""),
])
def test_classify_ats(url, expected_type, expected_host):
    assert classify_ats(url) == (expected_type, expected_host)
