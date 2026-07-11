from __future__ import annotations

import dataclasses
import threading
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import SessionLocal, get_db
from db.database import Config, ProfileConfig
from scraper.remotive import RemotiveSource
from scraper.remoteok import RemoteOKSource
from core.job import Job, JobState
from scraper.runner import run_scraper
from scraper.search import search_sources
from web.sse import send as _sse_send
from web.intake_pipeline import run_pipeline
from web.tenancy import current_profile_id
from web.auth.ext_token import bearer_or_session_profile

router = APIRouter(prefix="/api/scraper")

_SOURCES = {
    "remotive": RemotiveSource,
    "remoteok": RemoteOKSource,
}


def _get_enabled_source_ids(db: Session) -> list[str]:
    row = db.query(Config).filter_by(key="scraper_sources").first()
    if not row or not row.value.strip():
        return []
    return [s.strip() for s in row.value.split(",") if s.strip() in _SOURCES]


def _broadcast(event: str, data: Any) -> None:
    _sse_send(event, data)


def _run_in_background(source_ids: list[str], profile_id: int) -> None:
    db = SessionLocal()
    try:
        sources = [_SOURCES[sid]() for sid in source_ids]
        new_jobs = run_scraper(db, sources, profile_id)
        for job in new_jobs:
            job.intake()
            try:
                _broadcast("job", job.serialize())
            except Exception as exc:
                print(f"[scraper] broadcast failed for {job.job_key}: {exc}", flush=True)
            run_pipeline(job.job_key, profile_id)
    finally:
        db.close()


@router.post("/run")
def trigger_scrape(
    db: Session = Depends(get_db),
    profile_id: int = Depends(current_profile_id),
) -> dict[str, Any]:
    source_ids = _get_enabled_source_ids(db)

    if not source_ids:
        raise HTTPException(
            status_code=400,
            detail="No enabled sources configured. Set 'scraper_sources' in the config table.",
        )

    t = threading.Thread(target=_run_in_background, args=(source_ids, profile_id), daemon=True)
    t.start()
    return {"status": "started", "sources": source_ids}


class StageJobRequest(BaseModel):
    source: str
    job_key: str
    title: str
    company: str
    url: str
    description: str
    location: str = ""
    salary: str = ""
    remote: bool = False
    posted_at: str = ""
    scraped_at: str = ""


@router.post("/stage-job")
def stage_job(
    body: StageJobRequest,
    db: Session = Depends(get_db),
    profile_id: int = Depends(bearer_or_session_profile),
) -> dict[str, str]:
    """Stage a single job submitted by the browser extension.

    Accepts a job payload and persists it if not already present (deduped by URL).

    Args:
        body: Job data from the browser extension.
        db: SQLAlchemy session.
        profile_id: Owning tenant's profile id.

    Returns:
        Dict with 'status' ('staged' or 'duplicate') and 'job_key'.
    """
    from scraper.base import ScrapedJob
    scraped = ScrapedJob(
        source=body.source,
        job_key=body.job_key,
        title=body.title,
        company=body.company,
        url=body.url,
        description=body.description,
        location=body.location,
        salary=body.salary,
        remote=body.remote,
        posted_at=body.posted_at,
    )
    inserted_jobs = Job.save_batch_returning([scraped], db, profile_id)
    status = "staged" if inserted_jobs else "duplicate"
    for job in inserted_jobs:
        job.intake()
        try:
            _sse_send("job", job.serialize())
        except Exception as exc:
            print(f"[stage_job] broadcast failed for {job.job_key}: {exc}", flush=True)
        threading.Thread(target=run_pipeline, args=(job.job_key, profile_id), daemon=True).start()
    return {"status": status, "job_key": body.job_key}


_APPLIED_STATES = {
    JobState.APPLIED.value, JobState.CONTACT.value, JobState.REJECTED.value,
}
_SCRAPED_STATES = {
    JobState.NEW.value, JobState.PENDING_REVIEW.value, JobState.READY.value,
}


def _status_for(db: Session, urls: list[str], profile_id: int) -> dict[str, str]:
    """Map each url to its interaction status against the profile's jobs."""
    if not urls:
        return {}
    rows = (
        db.query(Job.url, Job.state)
        .filter(Job.profile_id == profile_id, Job.url.in_(urls))
        .all()
    )
    status: dict[str, str] = {}
    for url, state in rows:
        if state in _APPLIED_STATES:
            status[url] = "applied"
        elif state in _SCRAPED_STATES:
            status[url] = "scraped"
        else:  # deleted / anything else
            status[url] = "none"
    return status


def _profile_config_set(db: Session, key: str, value: str, profile_id: int) -> None:
    row = (
        db.query(ProfileConfig)
        .filter_by(profile_id=profile_id, key=key)
        .first()
    )
    if row:
        row.value = value
    else:
        db.add(ProfileConfig(profile_id=profile_id, key=key, value=value))
    db.commit()


class SearchRequest(BaseModel):
    query: str


@router.post("/search")
def search(
    body: SearchRequest,
    db: Session = Depends(get_db),
    profile_id: int = Depends(current_profile_id),
) -> dict[str, Any]:
    """Live-preview job search across the API sources (does not persist jobs).

    Runs the sources for the keyword, tags each candidate with its status
    relative to this profile's existing jobs, and remembers the query.
    """
    candidates = search_sources(body.query)
    status = _status_for(db, [c.url for c in candidates], profile_id)
    _profile_config_set(db, "last_job_search", body.query, profile_id)
    return {
        "query": body.query,
        "candidates": [
            {**dataclasses.asdict(c), "status": status.get(c.url, "none")}
            for c in candidates
        ],
    }


@router.get("/last-search")
def last_search(
    db: Session = Depends(get_db),
    profile_id: int = Depends(current_profile_id),
) -> dict[str, str]:
    """Return the profile's remembered Find Jobs query (empty if none)."""
    row = (
        db.query(ProfileConfig)
        .filter_by(profile_id=profile_id, key="last_job_search")
        .first()
    )
    return {"query": row.value if row else ""}
