from __future__ import annotations

import json
import warnings

from sqlalchemy.orm import Session

from core.types import JobState, SearchConfig
from db.models import Config, Job
from scraper.base import JobSource, ScrapedJob


def load_search_config(db: Session) -> SearchConfig:
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
    row = db.query(Config).filter_by(key="max_jobs_per_source").first()
    if row:
        try:
            return int(row.value)
        except (ValueError, TypeError):
            pass
    return 50


def save_jobs(db: Session, jobs: list[ScrapedJob]) -> int:
    count = 0
    for scraped in jobs:
        if db.query(Job).filter_by(url=scraped.url).first():
            continue
        db.add(Job(
            job_key=scraped.job_key,
            source=scraped.source,
            title=scraped.title,
            company=scraped.company,
            url=scraped.url,
            description=scraped.description,
            location=scraped.location,
            salary=scraped.salary,
            remote=scraped.remote,
            posted_at=scraped.posted_at,
            state=JobState.PENDING.value,
        ))
        count += 1
    db.commit()
    return count


def run_scraper(db: Session, sources: list[JobSource]) -> int:
    config = load_search_config(db)
    max_jobs = load_max_jobs(db)

    all_jobs: list[ScrapedJob] = []
    for source in sources:
        try:
            jobs = source.fetch(config, max_jobs)
            print(f"[scraper] {source.source_id}: fetched {len(jobs)} jobs")
            all_jobs.extend(jobs)
        except Exception as e:
            warnings.warn(f"[scraper] {source.source_id} failed: {e}")

    new_count = save_jobs(db, all_jobs)
    print(f"[scraper] saved {new_count} new jobs (skipped {len(all_jobs) - new_count} duplicates)")
    return new_count
