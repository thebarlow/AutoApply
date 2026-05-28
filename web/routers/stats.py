from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from core.job import Job
from core.session_cost import get_session_start
from db.database import get_db

router = APIRouter(prefix="/api")

_VALID_WINDOWS = {"session", "today", "week", "all_time"}
_ALL_STATES = ["new", "pending_review", "ready", "applied", "contact", "rejected"]


def _date_label(iso: str) -> str:
    """Return 'Mon D' label from ISO datetime string."""
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%b %#d")
    except (ValueError, TypeError):
        return iso[:10]


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
    scraped_q = db.query(Job)
    if cutoff_iso:
        scraped_q = scraped_q.filter(Job.scraped_at >= cutoff_iso)

    scraped_by_date: dict[str, int] = defaultdict(int)
    for job in scraped_q.all():
        if job.scraped_at:
            scraped_by_date[_date_label(job.scraped_at)] += 1

    # Resumes: bucket by resume_generated_at
    resume_q = db.query(Job).filter(Job.resume_generated_at.isnot(None))
    if cutoff_iso:
        resume_q = resume_q.filter(Job.resume_generated_at >= cutoff_iso)

    resumes_by_date: dict[str, int] = defaultdict(int)
    for job in resume_q.all():
        resumes_by_date[_date_label(job.resume_generated_at)] += 1

    # Covers: bucket by cover_generated_at
    cover_q = db.query(Job).filter(Job.cover_generated_at.isnot(None))
    if cutoff_iso:
        cover_q = cover_q.filter(Job.cover_generated_at >= cutoff_iso)

    covers_by_date: dict[str, int] = defaultdict(int)
    for job in cover_q.all():
        covers_by_date[_date_label(job.cover_generated_at)] += 1

    # Merge and sort labels
    all_labels = sorted(
        set(scraped_by_date) | set(resumes_by_date) | set(covers_by_date)
    )
    bars = [
        {
            "label": lbl,
            "scraped": scraped_by_date.get(lbl, 0),
            "resumes": resumes_by_date.get(lbl, 0),
            "covers": covers_by_date.get(lbl, 0),
        }
        for lbl in all_labels
    ]

    # by_state: pipeline snapshot, not window-filtered
    by_state = {s: db.query(Job).filter(Job.state == s).count() for s in _ALL_STATES}

    return {"bars": bars, "by_state": by_state}
