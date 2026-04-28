from __future__ import annotations

import threading
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import SessionLocal, get_db
from db.models import Config
from scraper.base import ScrapedJob
from scraper.remotive import RemotiveSource
from scraper.remoteok import RemoteOKSource
from scraper.runner import run_scraper, save_jobs

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


def _run_in_background(source_ids: list[str]) -> None:
    db = SessionLocal()
    try:
        sources = [_SOURCES[sid]() for sid in source_ids]
        run_scraper(db, sources)
    finally:
        db.close()


@router.post("/run")
def trigger_scrape(db: Session = Depends(get_db)) -> dict[str, Any]:
    source_ids = _get_enabled_source_ids(db)

    if not source_ids:
        raise HTTPException(
            status_code=400,
            detail="No enabled sources configured. Set 'scraper_sources' in the config table.",
        )

    t = threading.Thread(target=_run_in_background, args=(source_ids,), daemon=True)
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
def stage_job(body: StageJobRequest, db: Session = Depends(get_db)) -> dict[str, str]:
    # scraped_at is accepted for client compatibility but not stored; ScrapedJob has no such field.
    job = ScrapedJob(
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
    inserted = save_jobs(db, [job])
    status = "staged" if inserted > 0 else "duplicate"
    return {"status": status, "job_key": body.job_key}
