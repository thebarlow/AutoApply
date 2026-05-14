import pytest

from scraper.base import SearchConfig
from scraper.base import JobSource, ScrapedJob


def test_scraped_job_required_fields():
    job = ScrapedJob(
        source="remotive",
        job_key="remotive_1",
        title="Python Dev",
        company="Corp",
        url="https://example.com/1",
        description="Python required.",
    )
    assert job.source == "remotive"
    assert job.job_key == "remotive_1"
    assert job.title == "Python Dev"
    assert job.company == "Corp"
    assert job.url == "https://example.com/1"
    assert job.description == "Python required."


def test_scraped_job_defaults():
    job = ScrapedJob(
        source="remotive", job_key="remotive_1", title="Dev",
        company="Corp", url="https://example.com/1", description="desc",
    )
    assert job.location == ""
    assert job.salary == ""
    assert job.remote is False
    assert job.posted_at == ""


def test_scraped_job_optional_fields():
    job = ScrapedJob(
        source="remoteok", job_key="remoteok_99", title="SWE",
        company="Acme", url="https://example.com/99", description="Go dev",
        location="Remote", salary="$120k", remote=True, posted_at="2026-01-01",
    )
    assert job.location == "Remote"
    assert job.salary == "$120k"
    assert job.remote is True
    assert job.posted_at == "2026-01-01"


def test_job_source_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        JobSource()


def test_search_config_importable_from_scraper_base():
    from scraper.base import SearchConfig
    config = SearchConfig()
    assert config.keywords_whitelist == []
    assert config.remote_only is True
    assert config.full_time_only is True


def test_search_config_custom_values():
    from scraper.base import SearchConfig
    config = SearchConfig(keywords_whitelist=["python"], remote_only=False)
    assert config.keywords_whitelist == ["python"]
    assert config.remote_only is False
