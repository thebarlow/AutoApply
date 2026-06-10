from __future__ import annotations

import time
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from core.job import Job
from core.skill_analytics import aggregate_skill_frequency, job_has_skill
from core.user import User
from db.database import get_db, SkillAlias
from web.tenancy import current_profile_id

router = APIRouter(prefix="/api")

# Skill-frequency aggregation scans every extracted job and crunches it in
# Python, which is slow to redo on every dashboard mount. Cache the result and
# reuse it while the extracted-job count is unchanged, with a short TTL so
# re-extractions (which don't change the count) still refresh within a minute.
_SKILL_CACHE: dict = {"sig": None, "ts": 0.0, "result": None}
_SKILL_CACHE_TTL = 60.0


def _load_aliases(db: Session, profile_id: int) -> dict[str, str] | None:
    """Merged alias map: built-in _ALIASES plus this tenant's DB overrides.

    Returns None if the alias table is empty (signals callers to use _ALIASES
    directly, which is the same result but avoids an unnecessary dict copy).
    """
    from core.skill_analytics import _ALIASES
    rows = db.query(SkillAlias).filter_by(profile_id=profile_id).all()
    if not rows:
        return None
    merged = dict(_ALIASES)
    merged.update({row.alias_key: row.canonical for row in rows})
    return merged


def invalidate_skill_cache() -> None:
    """Reset the skill-frequency cache. Call after any alias mutation."""
    _SKILL_CACHE.update(sig=None, ts=0.0, result=None)

_VALID_WINDOWS = {"today", "week", "all_time"}
_ALL_STATES = ["new", "pending_review", "ready", "applied", "contact", "rejected"]


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
    if window == "today":
        cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif window == "week":
        cutoff = now - timedelta(days=7)
    else:
        cutoff = None

    cutoff_iso = cutoff.isoformat() if cutoff else None

    # by_state: pipeline snapshot, not window-filtered
    by_state = {s: db.query(Job).filter(Job.state == s).count() for s in _ALL_STATES}

    # totals: window-filtered counts driving the User-tab stat counter. Each
    # metric counts jobs whose corresponding timestamp falls within the window.
    def _count(column) -> int:
        q = db.query(Job).filter(column.isnot(None))
        if cutoff_iso:
            q = q.filter(column >= cutoff_iso)
        return q.count()

    totals = {
        "applied": _count(Job.applied_at),
        "scraped": _count(Job.scraped_at),
        "resumes": _count(Job.resume_generated_at),
    }

    return {"by_state": by_state, "totals": totals}


@router.get("/skill-frequency")
def get_skill_frequency(
    db: Session = Depends(get_db), profile_id: int = Depends(current_profile_id)
) -> dict:
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

    # Count before loading so a concurrent alias insert can't yield a map with N
    # rows signed under N+1 (and cached wrong) on READ COMMITTED backends.
    alias_sig = db.query(SkillAlias).filter_by(profile_id=profile_id).count()
    aliases = _load_aliases(db, profile_id)
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
    from core.skill_analytics import normalize_skill, skill_key
    key_to_display = {row["key"]: row["skill"] for row in agg["skills"]}
    profile_skills: list[str] = []
    try:
        user = User.load(db)
        seen: set[str] = set()
        for raw in getattr(user, "skills", []) or []:
            pk = skill_key(raw, aliases)
            # Prefer the chart's display so the "have" badge matches; fall back to
            # the plain normalized name for skills not present in any job.
            display = key_to_display.get(pk) or normalize_skill(raw, aliases)
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
    profile_id: int = Depends(current_profile_id),
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
    aliases = _load_aliases(db, profile_id)
    keys = [j.job_key for j in jobs if job_has_skill(j, skill, aliases)]
    return {"job_keys": keys}
