from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from core.job import Job
from scraper.base import JobSource, SearchConfig
from db.database import Config

logger = logging.getLogger(__name__)


def load_search_config(db: Session, profile_id: int) -> SearchConfig:
    """Load scraper search parameters, per-tenant keys from profile_config, rest global.

    Args:
        db: SQLAlchemy session.
        profile_id: Owning tenant's profile id (for the per-tenant keys).

    Returns:
        SearchConfig instance populated from stored config values.
    """
    from db.database import ProfileConfig
    from db.seed import PROFILE_CONFIG_DEFAULTS

    def _get(key: str, default: str = "") -> str:
        row = db.query(Config).filter_by(key=key).first()
        return row.value if row else default

    def _t(key: str) -> str:
        row = db.query(ProfileConfig).filter_by(profile_id=profile_id, key=key).first()
        return row.value if row else PROFILE_CONFIG_DEFAULTS.get(key, "")

    raw_salary = _get("target_salary_min", "0")
    try:
        salary_min = int(raw_salary) or None
    except (ValueError, TypeError):
        salary_min = None

    return SearchConfig(
        keywords_whitelist=json.loads(_t("keywords_whitelist")),
        keywords_blacklist=json.loads(_t("keywords_blacklist")),
        location=_get("location", ""),
        remote_only=_get("remote_only", "true").lower() == "true",
        full_time_only=_get("full_time_only", "true").lower() == "true",
        target_salary_min=salary_min,
        benefits_priorities=json.loads(_get("benefits_priorities", "[]")),
    )


def load_max_jobs(db: Session, profile_id: int) -> int:
    """Load the max_jobs_per_source config value for this tenant.

    Args:
        db: SQLAlchemy session.
        profile_id: Owning tenant's profile id.

    Returns:
        Integer limit, defaulting to 50.
    """
    from db.database import ProfileConfig
    from db.seed import PROFILE_CONFIG_DEFAULTS

    row = db.query(ProfileConfig).filter_by(profile_id=profile_id, key="max_jobs_per_source").first()
    if row:
        try:
            return int(row.value)
        except (ValueError, TypeError):
            pass
    try:
        return int(PROFILE_CONFIG_DEFAULTS["max_jobs_per_source"])
    except (ValueError, TypeError):
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
    config = load_search_config(db, profile_id)
    max_jobs = load_max_jobs(db, profile_id)

    all_scraped = []
    for source in sources:
        try:
            jobs = source.fetch(config, max_jobs)
            print(f"[scraper] {source.source_id}: fetched {len(jobs)} jobs")
            all_scraped.extend(jobs)
        except Exception:
            logger.exception("[scraper] %s failed", source.source_id)

    new_jobs = Job.save_batch_returning(all_scraped, db, profile_id)
    print(f"[scraper] saved {len(new_jobs)} new jobs (skipped {len(all_scraped) - len(new_jobs)} duplicates)")
    return new_jobs
