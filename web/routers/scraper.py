from __future__ import annotations

import dataclasses
import hashlib
import logging
import threading
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import get_db
from db.database import ProfileConfig
from core.ats import classify_ats
from core.job import Job, JobState
from scraper.search import search_sources
from web.sse import send as _sse_send
from web.intake_pipeline import run_pipeline
from web.tenancy import current_profile_id
from web.auth.ext_token import bearer_or_session_profile

router = APIRouter(prefix="/api/scraper")

logger = logging.getLogger(__name__)

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
    easy_apply: bool | None = None
    apply_url_raw: str = ""


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
        easy_apply=body.easy_apply,
        apply_url_raw=body.apply_url_raw,
    )
    inserted_jobs = Job.save_batch_returning([scraped], db, profile_id)
    status = "staged" if inserted_jobs else "duplicate"
    for job in inserted_jobs:
        if job.easy_apply:
            job.ats_type = "easy_apply"
            db.commit()
        job.intake()
        try:
            _sse_send("job", job.serialize(), profile_id=profile_id)
        except Exception:
            logger.exception("[stage_job] broadcast failed for %s", job.job_key)
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
            _sse_send("job", job.serialize(), profile_id=profile_id)
        except Exception:
            logger.exception("[scrape_selected] broadcast failed for %s", job.job_key)
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


def candidate_id(title: str, company: str, location: str) -> str:
    """Stable identity for a job posting, independent of source/tracking URL.

    Hashes the normalized title/company/location so the same posting maps to
    one id across sources and re-searches. Used to hide jobs the user has
    already scraped (present in inbox/archives) or deleted (client cache).
    """
    key = "|".join(
        [
            (title or "").strip().lower(),
            (company or "").strip().lower(),
            (location or "").strip().lower(),
        ]
    )
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


def _existing_candidate_ids(db: Session, profile_id: int) -> set[str]:
    """Candidate ids for the profile's non-deleted jobs (inbox + archives).

    Deleted jobs are treated as not-interacted, so they are excluded from the
    set and may resurface in a search.
    """
    rows = (
        db.query(Job.title, Job.company, Job.location)
        .filter(
            Job.profile_id == profile_id,
            Job.state != JobState.DELETED.value,
        )
        .all()
    )
    return {candidate_id(t, c, loc) for t, c, loc in rows}


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
    exclude: list[str] = []
    location: str = ""


@router.post("/search")
def search(
    body: SearchRequest,
    db: Session = Depends(get_db),
    profile_id: int = Depends(current_profile_id),
) -> dict[str, Any]:
    """Live-preview job search across the API sources (does not persist jobs).

    Runs the sources for the keyword, drops candidates the profile has
    already scraped (present in inbox/archives), stamps each survivor with a
    stable ``candidate_id``, and remembers the query, banned words, and
    location filter. Deleted-job filtering is handled client-side via a cached
    id list.
    """
    candidates = search_sources(
        body.query, exclude=body.exclude, location=body.location
    )
    existing = _existing_candidate_ids(db, profile_id)
    _profile_config_set(db, "last_job_search", body.query, profile_id)
    _profile_config_set(
        db, "last_job_exclude", ",".join(body.exclude), profile_id
    )
    _profile_config_set(db, "last_job_location", body.location, profile_id)
    out = []
    for c in candidates:
        cid = candidate_id(c.title, c.company, c.location)
        if cid in existing:
            continue  # already scraped/applied — hide it
        out.append({**dataclasses.asdict(c), "candidate_id": cid})
    return {"query": body.query, "candidates": out}


@router.get("/last-search")
def last_search(
    db: Session = Depends(get_db),
    profile_id: int = Depends(current_profile_id),
) -> dict[str, Any]:
    """Return the profile's remembered Find Jobs query/filters (empty if none)."""
    def _get(key: str) -> str:
        row = (
            db.query(ProfileConfig)
            .filter_by(profile_id=profile_id, key=key)
            .first()
        )
        return str(row.value) if row and row.value else ""

    exclude = _get("last_job_exclude")
    return {
        "query": _get("last_job_search"),
        "exclude": [w for w in exclude.split(",") if w] if exclude else [],
        "location": _get("last_job_location"),
    }


class AtsResolutionRequest(BaseModel):
    apply_url_resolved: str


@router.patch("/jobs/{job_key}/ats-resolution")
def resolve_ats(
    job_key: str,
    body: AtsResolutionRequest,
    db: Session = Depends(get_db),
    profile_id: int = Depends(bearer_or_session_profile),
) -> dict[str, Any]:
    """Classify a resolved apply URL and store the ATS result on the job.

    Called by the browser extension after it follows an external job's apply
    redirect to its final destination.

    Args:
        job_key: The job to update.
        body: The resolved apply URL.
        db: SQLAlchemy session.
        profile_id: Owning tenant's profile id (bearer or session).

    Returns:
        Dict with the updated ats_type, ats_domain, and apply_url_resolved.
    """
    job = Job.get(job_key, db, profile_id=profile_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    ats_type, host = classify_ats(body.apply_url_resolved)
    job.apply_url_resolved = body.apply_url_resolved
    job.ats_type = ats_type
    job.ats_domain = host
    db.commit()
    db.refresh(job)
    try:
        _sse_send("job", job.serialize(), profile_id=profile_id)
    except Exception:
        logger.exception("[resolve_ats] broadcast failed for %s", job_key)
    return {
        "job_key": job_key,
        "ats_type": job.ats_type,
        "ats_domain": job.ats_domain,
        "apply_url_resolved": job.apply_url_resolved,
    }
