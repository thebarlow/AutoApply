from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import anthropic as _anthropic
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.scorer import load_config as _load_config
from core.scorer import load_user_profile as _load_user_profile
from core.scorer import score_job as _score_job
from db.database import get_db
from db.models import Job
from generator.generator import generate_cover_for_job as _generate_cover_for_job
from generator.generator import generate_resume_for_job as _generate_resume_for_job


def _make_anthropic_client() -> _anthropic.Anthropic:
    return _anthropic.Anthropic()

router = APIRouter(prefix="/api/jobs")


class StateUpdate(BaseModel):
    state: str


def _serialize(job: Job) -> dict[str, Any]:
    justification = job.score_justification
    if isinstance(justification, str):
        try:
            justification = json.loads(justification)
        except (json.JSONDecodeError, TypeError):
            justification = {}

    return {
        "job_key": job.job_key,
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "salary": job.salary,
        "url": job.url,
        "description": job.description,
        "remote": job.remote,
        "state": job.state,
        "desirability_score": job.desirability_score,
        "fit_score": job.fit_score,
        "final_score": job.final_score,
        "score_justification": justification,
        "resume_path": job.resume_path,
        "cover_path": job.cover_path,
    }


@router.get("")
def get_jobs(db: Session = Depends(get_db)):
    jobs = db.query(Job).order_by(Job.final_score.desc()).all()
    return [_serialize(j) for j in jobs]


@router.patch("/{job_key}/state")
def update_job_state(job_key: str, body: StateUpdate, db: Session = Depends(get_db)):
    if body.state != "applied":
        raise HTTPException(status_code=400, detail=f"Invalid state: {body.state!r}")

    job = db.query(Job).filter(Job.job_key == job_key).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    job.state = body.state
    db.commit()
    db.refresh(job)
    return _serialize(job)


@router.post("/{job_key}/score")
def score_job_endpoint(job_key: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.job_key == job_key).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    profile = _load_user_profile(db)
    config = _load_config(db)
    client = _make_anthropic_client()
    _score_job(job, profile, config, client, db)
    db.refresh(job)
    return _serialize(job)


@router.post("/{job_key}/generate/resume")
def generate_resume_endpoint(job_key: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.job_key == job_key).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        _generate_resume_for_job(job_key, db=db, client=_make_anthropic_client())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    db.refresh(job)
    return _serialize(job)


@router.post("/{job_key}/generate/cover")
def generate_cover_endpoint(job_key: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.job_key == job_key).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        _generate_cover_for_job(job_key, db=db, client=_make_anthropic_client())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    db.refresh(job)
    return _serialize(job)


@router.get("/{job_key}/resume")
def serve_resume(job_key: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.job_key == job_key).first()
    if job is None or not job.resume_path:
        raise HTTPException(status_code=404, detail="Resume not found")
    path = Path(job.resume_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Resume file missing")
    return FileResponse(path, media_type="application/pdf")


@router.get("/{job_key}/cover")
def serve_cover(job_key: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.job_key == job_key).first()
    if job is None or not job.cover_path:
        raise HTTPException(status_code=404, detail="Cover letter not found")
    path = Path(job.cover_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Cover letter file missing")
    return FileResponse(path, media_type="application/pdf")


@router.delete("/{job_key}")
def delete_job(job_key: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.job_key == job_key).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    db.delete(job)
    db.commit()
    return {"deleted": job_key}
