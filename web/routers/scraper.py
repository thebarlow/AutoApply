from __future__ import annotations

import dataclasses
import threading
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import get_db
from db.database import ProfileConfig
from core.job import Job, JobState
from scraper.search import search_sources
from web.sse import send as _sse_send
from web.intake_pipeline import run_pipeline
from web.tenancy import current_profile_id
from web.auth.ext_token import bearer_or_session_profile

router = APIRouter(prefix="/api/scraper")

MAX_SCRAPE_BATCH = 25


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


class ScrapeSelectedRequest(BaseModel):
    jobs: list[StageJobRequest]


@router.post("/scrape-selected")
def scrape_selected(
    body: ScrapeSelectedRequest,
    db: Session = Depends(get_db),
    profile_id: int = Depends(current_profile_id),
) -> dict[str, Any]:
    """Persist the selected candidate jobs into the inbox and run the pipeline.

    Batched equivalent of ``stage-job``: dedupes by url, and for each newly
    inserted job runs intake + score/generate. Duplicates are reported, not
    errored.

    Args:
        body: The list of candidate jobs selected by the user.
        db: SQLAlchemy session.
        profile_id: Owning tenant's profile id.

    Returns:
        Dict with a 'results' list of {'job_key', 'status'} entries.
    """
    if len(body.jobs) > MAX_SCRAPE_BATCH:
        raise HTTPException(
            status_code=400,
            detail=f"Too many jobs selected (max {MAX_SCRAPE_BATCH}).",
        )

    from scraper.base import ScrapedJob

    scraped = [
        ScrapedJob(
            source=j.source, job_key=j.job_key, title=j.title, company=j.company,
            url=j.url, description=j.description, location=j.location,
            salary=j.salary, remote=j.remote, posted_at=j.posted_at,
        )
        for j in body.jobs
    ]
    inserted = Job.save_batch_returning(scraped, db, profile_id)
    inserted_keys = {job.job_key for job in inserted}
    for job in inserted:
        job.intake()
        try:
            _sse_send("job", job.serialize())
        except Exception as exc:
            print(f"[scrape_selected] broadcast failed for {job.job_key}: {exc}",
                  flush=True)
        threading.Thread(
            target=run_pipeline, args=(job.job_key, profile_id), daemon=True
        ).start()
    return {
        "results": [
            {"job_key": j.job_key,
             "status": "staged" if j.job_key in inserted_keys else "duplicate"}
            for j in body.jobs
        ]
    }


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
