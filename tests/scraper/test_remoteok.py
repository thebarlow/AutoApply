import pytest
from unittest.mock import MagicMock, patch

from scraper.base import SearchConfig
from scraper.remoteok import RemoteOKSource


def _config(**kwargs) -> SearchConfig:
    defaults = dict(
        keywords_whitelist=[], keywords_blacklist=[],
        location="", remote_only=True, full_time_only=True,
    )
    defaults.update(kwargs)
    return SearchConfig(**defaults)


def _mock_response(jobs: list[dict]) -> MagicMock:
    m = MagicMock()
    # First element is always a metadata object (no "id" key)
    m.json.return_value = [{"legal": "RemoteOK API"}] + jobs
    m.raise_for_status.return_value = None
    return m


def _api_job(
    id="123", position="Python Dev", company="Corp",
    url="https://remoteok.com/remote-jobs/123",
    description="Python required.",
    location="Remote", date="2026-01-15T00:00:00Z",
) -> dict:
    return dict(
        id=id, position=position, company=company, url=url,
        description=description, location=location, date=date,
    )


def test_remoteok_source_id():
    assert RemoteOKSource().source_id == "remoteok"


def test_remoteok_maps_fields_correctly():
    with patch("scraper.remoteok.httpx.get", return_value=_mock_response([_api_job()])):
        results = RemoteOKSource().fetch(_config(), max_jobs=10)

    assert len(results) == 1
    job = results[0]
    assert job.source == "remoteok"
    assert job.job_key == "remoteok_123"
    assert job.title == "Python Dev"
    assert job.company == "Corp"
    assert job.url == "https://remoteok.com/remote-jobs/123"
    assert job.description == "Python required."
    assert job.location == "Remote"
    assert job.remote is True
    assert job.posted_at == "2026-01-15T00:00:00Z"


def test_remoteok_skips_metadata_element():
    raw = MagicMock()
    raw.raise_for_status.return_value = None
    raw.json.return_value = [
        {"legal": "metadata, no id key"},
        _api_job(id="1", url="https://remoteok.com/remote-jobs/1"),
    ]
    with patch("scraper.remoteok.httpx.get", return_value=raw):
        results = RemoteOKSource().fetch(_config(), max_jobs=10)

    assert len(results) == 1
    assert results[0].job_key == "remoteok_1"


def test_remoteok_filters_by_whitelist():
    jobs = [
        _api_job(id="1", position="Python Dev", url="https://remoteok.com/remote-jobs/1"),
        _api_job(id="2", position="Java Engineer", description="Java experience required.", url="https://remoteok.com/remote-jobs/2"),
    ]
    with patch("scraper.remoteok.httpx.get", return_value=_mock_response(jobs)):
        results = RemoteOKSource().fetch(_config(keywords_whitelist=["python"]), max_jobs=10)

    assert len(results) == 1
    assert results[0].job_key == "remoteok_1"


def test_remoteok_no_whitelist_keeps_all():
    jobs = [
        _api_job(id="1", url="https://remoteok.com/remote-jobs/1"),
        _api_job(id="2", url="https://remoteok.com/remote-jobs/2"),
    ]
    with patch("scraper.remoteok.httpx.get", return_value=_mock_response(jobs)):
        results = RemoteOKSource().fetch(_config(keywords_whitelist=[]), max_jobs=10)

    assert len(results) == 2


def test_remoteok_filters_blacklist_terms():
    jobs = [
        _api_job(id="1", position="Senior Python Dev", url="https://remoteok.com/remote-jobs/1"),
        _api_job(id="2", position="Python Dev", url="https://remoteok.com/remote-jobs/2"),
    ]
    with patch("scraper.remoteok.httpx.get", return_value=_mock_response(jobs)):
        results = RemoteOKSource().fetch(_config(keywords_blacklist=["senior"]), max_jobs=10)

    assert len(results) == 1
    assert results[0].job_key == "remoteok_2"


def test_remoteok_respects_max_jobs():
    jobs = [_api_job(id=str(i), url=f"https://remoteok.com/remote-jobs/{i}") for i in range(10)]
    with patch("scraper.remoteok.httpx.get", return_value=_mock_response(jobs)):
        results = RemoteOKSource().fetch(_config(), max_jobs=3)

    assert len(results) == 3


def test_remoteok_skips_jobs_without_url():
    jobs = [
        dict(id="1", position="Dev", company="Corp", url="",
             description="desc", location="", date=""),
        _api_job(id="2", url="https://remoteok.com/remote-jobs/2"),
    ]
    with patch("scraper.remoteok.httpx.get", return_value=_mock_response(jobs)):
        results = RemoteOKSource().fetch(_config(), max_jobs=10)

    assert len(results) == 1
    assert results[0].job_key == "remoteok_2"
