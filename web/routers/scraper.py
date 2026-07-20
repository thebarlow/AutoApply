from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
import threading
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import get_db
from db.database import ProfileConfig
from core.application_mapper import build_plan, needs_essay_pass
from core.ats import classify_ats, unwrap_apply_url
from core.job import Job, JobState
from core.metering import meter_action
from core.pricing import price_for
from core.schemas import EnumeratedField
from core.user import User
from scraper.search import search_sources
from web.application_plan_service import EssayDraftError, make_essay_drafter
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
        elif body.apply_url_raw:
            # LinkedIn wraps external apply links in a click-through interstitial
            # that headless tab resolution can't follow. The real target is in
            # the wrapper's url= param, so classify it now when it names a known
            # ATS — no redirect resolution needed.
            target = unwrap_apply_url(body.apply_url_raw)
            ats_type, host = classify_ats(target)
            if ats_type != "other":
                job.ats_type = ats_type
                job.ats_domain = host
                job.apply_url_resolved = target
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
    resolved = body.apply_url_resolved
    ats_type, host = classify_ats(unwrap_apply_url(resolved))
    if ats_type == "other" and job.apply_url_raw:
        # The extension may have stalled on an interstitial (e.g. LinkedIn's
        # safety redirect) that never reached the real ATS. Fall back to the
        # scrape-time apply URL, whose wrapper carries the true destination.
        alt_target = unwrap_apply_url(job.apply_url_raw)
        alt_type, alt_host = classify_ats(alt_target)
        if alt_type != "other":
            ats_type, host, resolved = alt_type, alt_host, alt_target
    job.apply_url_resolved = resolved
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


class ApplicationPlanRequest(BaseModel):
    enumerated_fields: list[EnumeratedField] = []


def _documents_for(job: Job) -> dict[str, str]:
    """Resume file pointer + cover letter text for plan resolution."""
    cover_text = ""
    if job.cover_path:
        try:
            from pathlib import Path
            cover_text = Path(job.cover_path).read_text(encoding="utf-8")
        except OSError:
            cover_text = ""
    return {"resume_file": job.resume_path or "", "cover_letter_text": cover_text}


@router.post("/jobs/{job_key}/application-plan")
def compute_application_plan(
    job_key: str,
    body: ApplicationPlanRequest,
    db: Session = Depends(get_db),
    profile_id: int = Depends(bearer_or_session_profile),
) -> dict[str, Any]:
    """Compute, persist, and return the application plan for a job's form.

    Args:
        job_key: The job whose application form is being mapped.
        body: Optionally the fields the extension enumerated off the live page.
        db: SQLAlchemy session.
        profile_id: Owning tenant's profile id (bearer or session).

    Returns:
        The computed ApplicationPlan, serialized.
    """
    job = Job.get(job_key, db, profile_id=profile_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    user = User.load(db, profile_id=profile_id)
    documents = _documents_for(job)
    fields = body.enumerated_fields

    if needs_essay_pass(job, fields):
        try:
            with meter_action(db, profile_id, action="map_fields", job_key=job_key,
                              price=price_for("map_fields")):
                plan = build_plan(job, user, documents, enumerated_fields=fields,
                                  draft_essays=make_essay_drafter(user, job))
        except EssayDraftError:
            # LLM drafting failed; meter_action refunded the debit. Still return
            # the deterministic plan (essay fields left undrafted), unmetered.
            plan = build_plan(job, user, documents, enumerated_fields=fields)
    else:
        plan = build_plan(job, user, documents, enumerated_fields=fields)

    job.application_plan = plan.model_dump_json()
    db.commit()
    db.refresh(job)
    try:
        _sse_send("job", job.serialize(), profile_id=profile_id)
    except Exception:
        logger.exception("[application-plan] broadcast failed for %s", job_key)
    return plan.model_dump()


@router.get("/jobs/{job_key}/application-plan")
def get_application_plan(
    job_key: str,
    db: Session = Depends(get_db),
    profile_id: int = Depends(bearer_or_session_profile),
) -> dict[str, Any]:
    """Return the last stored plan and the answers-completeness flag.

    Args:
        job_key: The job to look up.
        db: SQLAlchemy session.
        profile_id: Owning tenant's profile id (bearer or session).

    Returns:
        Dict with the stored plan (or null if never computed) and whether the
        profile's application_answers cover the eligibility/EEO fields.
    """
    job = Job.get(job_key, db, profile_id=profile_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    user = User.load(db, profile_id=profile_id)
    plan = json.loads(job.application_plan) if job.application_plan else None
    return {"plan": plan, "application_answers_complete": user.application_answers_complete()}
