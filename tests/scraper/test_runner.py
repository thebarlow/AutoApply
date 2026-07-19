import json
import logging

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.job import Job, JobState
from scraper.base import SearchConfig, JobSource, ScrapedJob
from db.database import Base, Config, ProfileConfig
from scraper.runner import (
    load_max_jobs,
    load_search_config,
    run_scraper,
)


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


def _scraped(n: int = 1) -> ScrapedJob:
    return ScrapedJob(
        source="remotive",
        job_key=f"remotive_{n}",
        title="Python Dev",
        company="Corp",
        url=f"https://example.com/job/{n}",
        description="desc",
        remote=True,
    )


class _MockSource(JobSource):
    def __init__(self, source_id: str, jobs: list[ScrapedJob]):
        self._id = source_id
        self._jobs = jobs

    @property
    def source_id(self) -> str:
        return self._id

    def fetch(self, config: SearchConfig, max_jobs: int) -> list[ScrapedJob]:
        return self._jobs


class _FailingSource(JobSource):
    @property
    def source_id(self) -> str:
        return "failing"

    def fetch(self, config: SearchConfig, max_jobs: int) -> list[ScrapedJob]:
        raise RuntimeError("network error")


# --- save_jobs ---

def test_save_jobs_inserts_new_jobs(db_session):
    count = len(Job.save_batch_returning([_scraped(1), _scraped(2)], db_session, profile_id=1))
    assert count == 2
    assert db_session.query(Job).count() == 2


def test_save_jobs_deduplicates_by_url(db_session):
    Job.save_batch_returning([_scraped(1)], db_session, profile_id=1)
    count = len(Job.save_batch_returning([_scraped(1), _scraped(2)], db_session, profile_id=1))
    assert count == 1
    assert db_session.query(Job).count() == 2


def test_save_jobs_sets_scraped_state(db_session):
    Job.save_batch_returning([_scraped(1)], db_session, profile_id=1)
    job = db_session.query(Job).first()
    assert job.state == JobState.NEW.value


def test_save_jobs_maps_all_fields(db_session):
    scraped = ScrapedJob(
        source="remotive", job_key="remotive_42", title="SWE",
        company="Acme", url="https://example.com/42",
        description="Python expert", location="Remote",
        salary="$120k", remote=True, posted_at="2026-01-01",
    )
    Job.save_batch_returning([scraped], db_session, profile_id=1)
    job = db_session.query(Job).first()
    assert job.job_key == "remotive_42"
    assert job.source == "remotive"
    assert job.title == "SWE"
    assert job.company == "Acme"
    assert job.location == "Remote"
    assert job.salary == "$120k"
    assert job.remote is True
    assert job.posted_at == "2026-01-01"


# --- run_scraper ---

def test_run_scraper_aggregates_sources(db_session):
    sources = [
        _MockSource("remotive", [_scraped(1), _scraped(2)]),
        _MockSource("remoteok", [_scraped(3)]),
    ]
    new_jobs = run_scraper(db_session, sources, profile_id=1)
    assert len(new_jobs) == 3
    assert db_session.query(Job).count() == 3


def test_run_scraper_continues_on_source_error(db_session, caplog):
    sources = [_FailingSource(), _MockSource("remoteok", [_scraped(1)])]
    with caplog.at_level(logging.ERROR, logger="scraper.runner"):
        new_jobs = run_scraper(db_session, sources, profile_id=1)
    assert len(new_jobs) == 1
    assert any("failing" in r.getMessage() for r in caplog.records)


# --- load_search_config ---

def test_load_search_config_from_db(db_session):
    db_session.add(ProfileConfig(profile_id=1, key="keywords_whitelist", value='["python", "django"]'))
    db_session.add(ProfileConfig(profile_id=1, key="keywords_blacklist", value='["senior"]'))
    db_session.add(Config(key="remote_only", value="true"))
    db_session.add(Config(key="full_time_only", value="false"))
    db_session.add(Config(key="location", value="New York"))
    db_session.add(Config(key="benefits_priorities", value='["401k"]'))
    db_session.commit()

    config = load_search_config(db_session, profile_id=1)
    assert config.keywords_whitelist == ["python", "django"]
    assert config.keywords_blacklist == ["senior"]
    assert config.remote_only is True
    assert config.full_time_only is False
    assert config.location == "New York"
    assert config.benefits_priorities == ["401k"]


def test_load_search_config_uses_defaults_when_missing(db_session):
    config = load_search_config(db_session, profile_id=1)
    assert config.keywords_whitelist == []
    assert config.keywords_blacklist == []
    assert config.remote_only is True


# --- load_max_jobs ---

def test_load_max_jobs_defaults_to_50(db_session):
    assert load_max_jobs(db_session, profile_id=1) == 50


def test_load_max_jobs_from_db(db_session):
    db_session.add(ProfileConfig(profile_id=1, key="max_jobs_per_source", value="25"))
    db_session.commit()
    assert load_max_jobs(db_session, profile_id=1) == 25


def test_load_search_config_target_salary_min(db_session):
    # "0" should become None (falsy int treated as no minimum)
    db_session.add(Config(key="target_salary_min", value="0"))
    db_session.commit()
    config = load_search_config(db_session, profile_id=1)
    assert config.target_salary_min is None

    # Valid non-zero integer should be preserved
    db_session.query(Config).filter_by(key="target_salary_min").delete()
    db_session.add(Config(key="target_salary_min", value="100000"))
    db_session.commit()
    config2 = load_search_config(db_session, profile_id=1)
    assert config2.target_salary_min == 100000
