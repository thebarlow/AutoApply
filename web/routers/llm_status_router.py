from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db.database import get_db
from core.job import Job
from web import llm_status

router = APIRouter(prefix="/api")


@router.get("/llm-status")
def get_llm_status(db: Session = Depends(get_db)) -> dict:
    job_keys = llm_status.snapshot()
    actions = llm_status.action_snapshot()

    jobs = (
        db.query(Job).filter(Job.job_key.in_(job_keys)).all()
        if job_keys else []
    )
    display = {j.job_key: {"title": j.title or "", "company": j.company or ""} for j in jobs}

    in_flight = [
        {
            "job_key": jk,
            "title": display.get(jk, {}).get("title", jk),
            "company": display.get(jk, {}).get("company", ""),
            "actions": actions.get(jk, []),
        }
        for jk in job_keys
    ]

    return {
        "processing": job_keys,
        "actions": actions,
        "in_flight": in_flight,
    }
