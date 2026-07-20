import pytest
from core.ats import classify_ats, unwrap_apply_url


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


@pytest.mark.parametrize("url,expected", [
    # LinkedIn safety wrapper -> decoded target
    (
        "https://www.linkedin.com/safety/go/?url=https%3A%2F%2Fjobs.ashbyhq.com%2Fsolace%2Fabc&urlhash=x",
        "https://jobs.ashbyhq.com/solace/abc",
    ),
    (
        "https://linkedin.com/safety/go/?url=https%3A%2F%2Fboards.greenhouse.io%2Facme%2F9",
        "https://boards.greenhouse.io/acme/9",
    ),
    # Not a wrapper: returned unchanged
    ("https://jobs.ashbyhq.com/solace/abc", "https://jobs.ashbyhq.com/solace/abc"),
    ("https://careers.acme.com/apply/1", "https://careers.acme.com/apply/1"),
    # Wrapper host but no url param: unchanged (nothing to unwrap)
    ("https://www.linkedin.com/safety/go/?_l=en_US", "https://www.linkedin.com/safety/go/?_l=en_US"),
    # linkedin.com host but not a safety-go path: unchanged
    ("https://www.linkedin.com/jobs/view/123?url=https%3A%2F%2Fx.com", "https://www.linkedin.com/jobs/view/123?url=https%3A%2F%2Fx.com"),
    # Malformed / empty: unchanged
    ("", ""),
    ("not a url", "not a url"),
])
def test_unwrap_apply_url(url, expected):
    assert unwrap_apply_url(url) == expected


def test_unwrap_then_classify_linkedin_wrapped_ashby():
    wrapped = "https://www.linkedin.com/safety/go/?url=https%3A%2F%2Fjobs.ashbyhq.com%2Fsolace%2Fabc"
    assert classify_ats(unwrap_apply_url(wrapped)) == ("ashby", "jobs.ashbyhq.com")
