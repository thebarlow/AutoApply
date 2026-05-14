import pytest
from unittest.mock import MagicMock, patch

from scraper.base import SearchConfig
from scraper.remotive import RemotiveSource


def _config(**kwargs) -> SearchConfig:
    defaults = dict(
        keywords_whitelist=[], keywords_blacklist=[],
        location="", remote_only=True, full_time_only=True,
    )
    defaults.update(kwargs)
    return SearchConfig(**defaults)


def _mock_response(jobs: list[dict]) -> MagicMock:
    m = MagicMock()
    m.json.return_value = {"jobs": jobs}
    m.raise_for_status.return_value = None
    return m


def _api_job(
    id=1, title="Python Dev", company="Corp",
    url="https://remotive.com/remote-jobs/1",
    description="Python required.",
    location="Worldwide", salary="$100k–$120k",
    publication_date="2026-01-15",
) -> dict:
    return dict(
        id=id, title=title, company_name=company, url=url,
        description=description, candidate_required_location=location,
        salary=salary, publication_date=publication_date,
    )


def test_remotive_source_id():
    assert RemotiveSource().source_id == "remotive"


def test_remotive_maps_fields_correctly():
    with patch("scraper.remotive.httpx.get", return_value=_mock_response([_api_job()])):
        results = RemotiveSource().fetch(_config(), max_jobs=10)

    assert len(results) == 1
    job = results[0]
    assert job.source == "remotive"
    assert job.job_key == "remotive_1"
    assert job.title == "Python Dev"
    assert job.company == "Corp"
    assert job.url == "https://remotive.com/remote-jobs/1"
    assert job.description == "Python required."
    assert job.location == "Worldwide"
    assert job.salary == "$100k–$120k"
    assert job.remote is True
    assert job.posted_at == "2026-01-15"


def test_remotive_filters_blacklist_in_title():
    jobs = [
        _api_job(id=1, title="Senior Python Dev", url="https://remotive.com/remote-jobs/1"),
        _api_job(id=2, title="Python Dev", url="https://remotive.com/remote-jobs/2"),
    ]
    with patch("scraper.remotive.httpx.get", return_value=_mock_response(jobs)):
        results = RemotiveSource().fetch(_config(keywords_blacklist=["senior"]), max_jobs=10)

    assert len(results) == 1
    assert results[0].job_key == "remotive_2"


def test_remotive_filters_blacklist_in_description():
    jobs = [
        _api_job(id=1, description="Must have 10+ years senior experience.", url="https://remotive.com/remote-jobs/1"),
        _api_job(id=2, description="Junior Python role.", url="https://remotive.com/remote-jobs/2"),
    ]
    with patch("scraper.remotive.httpx.get", return_value=_mock_response(jobs)):
        results = RemotiveSource().fetch(_config(keywords_blacklist=["senior"]), max_jobs=10)

    assert len(results) == 1
    assert results[0].job_key == "remotive_2"


def test_remotive_sends_first_whitelist_keyword():
    with patch("scraper.remotive.httpx.get", return_value=_mock_response([])) as mock_get:
        RemotiveSource().fetch(_config(keywords_whitelist=["python", "django"]), max_jobs=10)

    params = mock_get.call_args[1]["params"]
    assert params["search"] == "python"


def test_remotive_sends_empty_search_when_no_whitelist():
    with patch("scraper.remotive.httpx.get", return_value=_mock_response([])) as mock_get:
        RemotiveSource().fetch(_config(keywords_whitelist=[]), max_jobs=5)

    params = mock_get.call_args[1]["params"]
    assert params["search"] == ""
    assert params["limit"] == 5


def test_remotive_skips_jobs_without_url():
    jobs = [
        dict(id=1, title="Dev", company_name="Corp", url="", description="desc",
             candidate_required_location="", salary="", publication_date=""),
        _api_job(id=2, url="https://remotive.com/remote-jobs/2"),
    ]
    with patch("scraper.remotive.httpx.get", return_value=_mock_response(jobs)):
        results = RemotiveSource().fetch(_config(), max_jobs=10)

    assert len(results) == 1
    assert results[0].job_key == "remotive_2"
