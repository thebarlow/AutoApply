from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from core.job import Job
from core.skill_analytics import aggregate_skill_frequency, job_has_skill
from core.session_cost import get_session_start
from core.user import User
from db.database import get_db, SkillAlias

router = APIRouter(prefix="/api")

# Skill-frequency aggregation scans every extracted job and crunches it in
# Python, which is slow to redo on every dashboard mount. Cache the result and
# reuse it while the extracted-job count is unchanged, with a short TTL so
# re-extractions (which don't change the count) still refresh within a minute.
_SKILL_CACHE: dict = {"sig": None, "ts": 0.0, "result": None}
_SKILL_CACHE_TTL = 60.0


def _load_aliases(db: Session) -> dict[str, str] | None:
    """Merged alias map: built-in _ALIASES plus DB overrides.

    Returns None if the alias table is empty (signals callers to use _ALIASES
    directly, which is the same result but avoids an unnecessary dict copy).
    """
    from core.skill_analytics import _ALIASES
    rows = db.query(SkillAlias).all()
    if not rows:
        return None
    merged = dict(_ALIASES)
    merged.update({row.alias_key: row.canonical for row in rows})
    return merged


def invalidate_skill_cache() -> None:
    """Reset the skill-frequency cache. Call after any alias mutation."""
    _SKILL_CACHE.update(sig=None, ts=0.0, result=None)

_VALID_WINDOWS = {"session", "today", "week", "all_time"}
_ALL_STATES = ["new", "pending_review", "ready", "applied", "contact", "rejected"]


def _date_label(date_str: str) -> str:
    """Convert YYYY-MM-DD to 'Mon D' display label."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%b %#d")
    except (ValueError, TypeError):
        return date_str


def _iso_to_date(iso: str) -> str:
    """Extract YYYY-MM-DD from an ISO datetime string."""
    return iso[:10] if iso else ""


@router.get("/stats")
def get_stats(
    window: str = Query(...),
    db: Session = Depends(get_db),
) -> dict:
    if window not in _VALID_WINDOWS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid window: {window!r}. Must be one of {sorted(_VALID_WINDOWS)}",
        )

    now = datetime.now(timezone.utc)
    if window == "session":
        cutoff = get_session_start()
    elif window == "today":
        cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif window == "week":
        cutoff = now - timedelta(days=7)
    else:
        cutoff = None

    cutoff_iso = cutoff.isoformat() if cutoff else None

    # Scraped: bucket by scraped_at date
    scraped_q = db.query(Job).filter(Job.scraped_at.isnot(None))
    if cutoff_iso:
        scraped_q = scraped_q.filter(Job.scraped_at >= cutoff_iso)

    scraped_by_date: dict[str, int] = defaultdict(int)
    for job in scraped_q.all():
        scraped_by_date[_iso_to_date(job.scraped_at)] += 1

    # Resumes: bucket by resume_generated_at
    resume_q = db.query(Job).filter(Job.resume_generated_at.isnot(None))
    if cutoff_iso:
        resume_q = resume_q.filter(Job.resume_generated_at >= cutoff_iso)

    resumes_by_date: dict[str, int] = defaultdict(int)
    for job in resume_q.all():
        resumes_by_date[_iso_to_date(job.resume_generated_at)] += 1

    # Covers: bucket by cover_generated_at
    cover_q = db.query(Job).filter(Job.cover_generated_at.isnot(None))
    if cutoff_iso:
        cover_q = cover_q.filter(Job.cover_generated_at >= cutoff_iso)

    covers_by_date: dict[str, int] = defaultdict(int)
    for job in cover_q.all():
        covers_by_date[_iso_to_date(job.cover_generated_at)] += 1

    # Merge date keys (YYYY-MM-DD) and sort chronologically
    all_dates = sorted(
        set(scraped_by_date) | set(resumes_by_date) | set(covers_by_date)
    )
    bars = [
        {
            "label": _date_label(d),
            "scraped": scraped_by_date.get(d, 0),
            "resumes": resumes_by_date.get(d, 0),
            "covers": covers_by_date.get(d, 0),
        }
        for d in all_dates
    ]

    # by_state: pipeline snapshot, not window-filtered
    by_state = {s: db.query(Job).filter(Job.state == s).count() for s in _ALL_STATES}

    return {"bars": bars, "by_state": by_state}


@router.get("/skill-frequency")
def get_skill_frequency(db: Session = Depends(get_db)) -> dict:
    """Skill frequency across all jobs that have extraction data.

    Not window-filtered. A job counts as extracted when it has any extraction
    field populated. Includes ``profile_skills``: the active user's skills,
    normalized to canonical names, so the UI can flag which in-demand skills the
    profile already covers.
    """
    extracted_filter = and_(
        Job.state != "deleted",
        or_(
            Job.ext_required_skills.isnot(None),
            Job.ext_preferred_skills.isnot(None),
            Job.ext_tech_stack.isnot(None),
            Job.ext_seniority.isnot(None),
        ),
    )

    aliases = _load_aliases(db)
    alias_sig = db.query(SkillAlias).count()
    sig = (db.query(Job).filter(extracted_filter).count(), alias_sig)
    now = time.monotonic()
    cached = _SKILL_CACHE["result"]
    if (
        cached is not None
        and _SKILL_CACHE["sig"] == sig
        and now - _SKILL_CACHE["ts"] < _SKILL_CACHE_TTL
    ):
        agg = cached
    else:
        jobs = db.query(Job).filter(extracted_filter).all()
        # Treat empty strings as "no extraction" too (DB may store "" not NULL).
        extracted = [
            j
            for j in jobs
            if (
                j.ext_required_skills
                or j.ext_preferred_skills
                or j.ext_tech_stack
                or j.ext_seniority
            )
        ]
        agg = aggregate_skill_frequency(extracted, aliases=aliases)
        _SKILL_CACHE.update(sig=sig, ts=now, result=agg)

    # Profile skills are cheap to compute and profile-specific, so resolve them
    # fresh (outside the job-aggregation cache).
    from core.skill_analytics import skill_key
    key_to_display = {row["key"]: row["skill"] for row in agg["skills"]}
    profile_skills: list[str] = []
    try:
        user = User.load(db)
        seen: set[str] = set()
        for raw in getattr(user, "skills", []) or []:
            pk = skill_key(raw, aliases)
            display = key_to_display.get(pk)
            if display and display not in seen:
                seen.add(display)
                profile_skills.append(display)
    except Exception:
        profile_skills = []

    return {**agg, "profile_skills": profile_skills}


@router.get("/skill-frequency/jobs")
def get_jobs_for_skill(
    skill: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
) -> dict:
    """Job keys for all jobs whose extraction data lists the given skill.

    ``skill`` is the canonical display name shown in the chart (e.g. "Python").
    Matching is normalized, so raw tokens like "py" or "k8s" match.
    """
    jobs = (
        db.query(Job)
        .filter(
            Job.state != "deleted",
            or_(
                Job.ext_required_skills.isnot(None),
                Job.ext_preferred_skills.isnot(None),
                Job.ext_tech_stack.isnot(None),
                # Mirrors the extracted-job filter in get_skill_frequency; a
                # seniority-only job simply won't match job_has_skill below.
                Job.ext_seniority.isnot(None),
            ),
        )
        .all()
    )
    aliases = _load_aliases(db)
    keys = [j.job_key for j in jobs if job_has_skill(j, skill, aliases)]
    return {"job_keys": keys}
