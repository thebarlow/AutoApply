from __future__ import annotations

import json
import warnings

from sqlalchemy.orm import Session

from core.job import Job
from scraper.base import JobSource, SearchConfig
from db.database import Config


def load_search_config(db: Session) -> SearchConfig:
    """Load scraper search parameters from the Config table.

    Args:
        db: SQLAlchemy session.

    Returns:
        SearchConfig instance populated from stored config values.
    """
    def _get(key: str, default: str = "") -> str:
        row = db.query(Config).filter_by(key=key).first()
        return row.value if row else default

    raw_salary = _get("target_salary_min", "0")
    try:
        salary_min = int(raw_salary) or None
    except (ValueError, TypeError):
        salary_min = None

    return SearchConfig(
        keywords_whitelist=json.loads(_get("keywords_whitelist", "[]")),
        keywords_blacklist=json.loads(_get("keywords_blacklist", "[]")),
        location=_get("location", ""),
        remote_only=_get("remote_only", "true").lower() == "true",
        full_time_only=_get("full_time_only", "true").lower() == "true",
        target_salary_min=salary_min,
        benefits_priorities=json.loads(_get("benefits_priorities", "[]")),
    )


def load_max_jobs(db: Session) -> int:
    """Load the max_jobs_per_source config value.

    Args:
        db: SQLAlchemy session.

    Returns:
        Integer limit, defaulting to 50.
    """
    row = db.query(Config).filter_by(key="max_jobs_per_source").first()
    if row:
        try:
            return int(row.value)
        except (ValueError, TypeError):
            pass
    return 50


def run_scraper(db: Session, sources: list[JobSource], profile_id: int) -> list[Job]:
    """Fetch jobs from all sources and persist new ones.

    Args:
        db: SQLAlchemy session.
        sources: List of JobSource instances to fetch from.
        profile_id: Owning tenant's profile id.

    Returns:
        List of newly inserted Job objects.
    """
    config = load_search_config(db)
    max_jobs = load_max_jobs(db)

    all_scraped = []
    for source in sources:
        try:
            jobs = source.fetch(config, max_jobs)
            print(f"[scraper] {source.source_id}: fetched {len(jobs)} jobs")
            all_scraped.extend(jobs)
        except Exception as e:
            warnings.warn(f"[scraper] {source.source_id} failed: {e}")

    new_jobs = Job.save_batch_returning(all_scraped, db, profile_id)
    print(f"[scraper] saved {len(new_jobs)} new jobs (skipped {len(all_scraped) - len(new_jobs)} duplicates)")
    return new_jobs
