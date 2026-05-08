from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
import markdown as _markdown
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.llm import get_openai_client
from core.scorer import load_config as _load_config
from core.scorer import load_user_profile as _load_user_profile
from core.scorer import score_job as _score_job
from core.types import JobState
from db.database import get_db
from db.models import Config, Job
from generator.generator import generate_job as _generate_job
from generator.generator import generate_resume as _generate_resume
from generator.generator import generate_cover as _generate_cover
from generator.generator import generate_resume_md as _generate_resume_md
from generator.generator import generate_resume_pdf as _generate_resume_pdf
from generator.generator import generate_cover_md as _generate_cover_md
from generator.generator import generate_cover_pdf as _generate_cover_pdf
from generator.generator import build_resume_prompt, build_cover_prompt, build_description_prompt

_GENERATOR_OUTPUTS = Path(__file__).parent.parent.parent / "generator" / "outputs"


def _call_llm_for_extraction(client, model: str, prompt: str) -> str:
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content


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
        "resume_md_exists": (_GENERATOR_OUTPUTS / f"{job.job_key}_resume.md").exists(),
        "cover_md_exists": (_GENERATOR_OUTPUTS / f"{job.job_key}_cover.md").exists(),
        "extraction_md_exists": bool(job.extraction_md),
    }


@router.get("")
def get_jobs(db: Session = Depends(get_db)):
    jobs = db.query(Job).order_by(Job.final_score.desc()).all()
    return [_serialize(j) for j in jobs]


_VALID_STATES = {s.value for s in JobState}


@router.patch("/{job_key}/state")
def update_job_state(job_key: str, body: StateUpdate, db: Session = Depends(get_db)):
    if body.state not in _VALID_STATES:
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
    client, model = get_openai_client(db)
    _score_job(job, profile, config, client, model, db)
    db.refresh(job)
    return _serialize(job)


@router.post("/{job_key}/generate")
def generate_job_endpoint(job_key: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.job_key == job_key).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    client, model = get_openai_client(db)
    _generate_job(job_key, db=db, client=client, model=model)
    db.refresh(job)
    return _serialize(job)


@router.post("/{job_key}/generate/resume")
def generate_resume_endpoint(job_key: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.job_key == job_key).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    client, model = get_openai_client(db)
    _generate_resume(job_key, db=db, client=client, model=model)
    db.refresh(job)
    return _serialize(job)


@router.post("/{job_key}/generate/resume/md")
def generate_resume_md_endpoint(job_key: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.job_key == job_key).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    md_path = _GENERATOR_OUTPUTS / f"{job_key}_resume.md"
    md_path.unlink(missing_ok=True)
    client, model = get_openai_client(db)
    # Generator swallows exceptions and prints to stderr; file absence is our only failure signal.
    _generate_resume_md(job_key, db=db, client=client, model=model)
    if not md_path.exists():
        raise HTTPException(status_code=500, detail="Resume markdown generation failed")
    db.refresh(job)
    return _serialize(job)


@router.post("/{job_key}/generate/resume/pdf")
def generate_resume_pdf_endpoint(job_key: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.job_key == job_key).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    md_path = _GENERATOR_OUTPUTS / f"{job_key}_resume.md"
    if not md_path.exists():
        raise HTTPException(status_code=400, detail="Resume markdown must be generated first")
    # Generator swallows exceptions; job.resume_path absence after the call indicates failure.
    _generate_resume_pdf(job_key, db=db)
    db.refresh(job)
    if not job.resume_path:
        raise HTTPException(status_code=500, detail="Resume PDF rendering failed")
    return _serialize(job)


@router.post("/{job_key}/generate/cover")
def generate_cover_endpoint(job_key: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.job_key == job_key).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.resume_path:
        raise HTTPException(status_code=400, detail="Resume must be generated before cover letter")
    client, model = get_openai_client(db)
    _generate_cover(job_key, db=db, client=client, model=model)
    db.refresh(job)
    if job.cover_path is None:
        raise HTTPException(status_code=500, detail="Cover letter generation failed")
    return _serialize(job)


@router.post("/{job_key}/generate/cover/md")
def generate_cover_md_endpoint(job_key: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.job_key == job_key).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    md_path = _GENERATOR_OUTPUTS / f"{job_key}_cover.md"
    md_path.unlink(missing_ok=True)
    client, model = get_openai_client(db)
    # Generator swallows exceptions and prints to stderr; file absence is our only failure signal.
    _generate_cover_md(job_key, db=db, client=client, model=model)
    if not md_path.exists():
        raise HTTPException(status_code=500, detail="Cover letter markdown generation failed")
    db.refresh(job)
    return _serialize(job)


@router.post("/{job_key}/generate/cover/pdf")
def generate_cover_pdf_endpoint(job_key: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.job_key == job_key).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    # Cover letter PDF generation requires a resume PDF to exist first — enforced as a workflow gate
    # to ensure the applicant has a complete resume before submitting a cover letter.
    if not job.resume_path:
        raise HTTPException(status_code=400, detail="Resume PDF must be generated before cover letter PDF")
    md_path = _GENERATOR_OUTPUTS / f"{job_key}_cover.md"
    if not md_path.exists():
        raise HTTPException(status_code=400, detail="Cover letter markdown must be generated first")
    # Generator swallows exceptions; job.cover_path absence after the call indicates failure.
    _generate_cover_pdf(job_key, db=db)
    db.refresh(job)
    if job.cover_path is None:
        raise HTTPException(status_code=500, detail="Cover letter PDF rendering failed")
    return _serialize(job)


@router.get("/{job_key}/resume")
def serve_resume(job_key: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.job_key == job_key).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.resume_path:
        raise HTTPException(status_code=404, detail="Resume not found")
    path = Path(job.resume_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Resume file missing")
    return FileResponse(path, media_type="application/pdf")


@router.get("/{job_key}/cover")
def serve_cover(job_key: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.job_key == job_key).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.cover_path:
        raise HTTPException(status_code=404, detail="Cover letter not found")
    path = Path(job.cover_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Cover letter file missing")
    return FileResponse(path, media_type="application/pdf")


@router.get("/{job_key}/resume/markdown", response_class=PlainTextResponse)
def serve_resume_markdown(job_key: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.job_key == job_key).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    path = _GENERATOR_OUTPUTS / f"{job_key}_resume.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Resume markdown not found")
    return path.read_text(encoding="utf-8")


@router.get("/{job_key}/cover/markdown", response_class=PlainTextResponse)
def serve_cover_markdown(job_key: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.job_key == job_key).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    path = _GENERATOR_OUTPUTS / f"{job_key}_cover.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Cover letter markdown not found")
    return path.read_text(encoding="utf-8")


@router.get("/{job_key}/resume/prompt", response_class=PlainTextResponse)
def get_resume_prompt(job_key: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.job_key == job_key).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    profile = _load_user_profile(db)
    tpl = db.query(Config).filter_by(key="resume_prompt_template").first()
    if not tpl:
        raise HTTPException(status_code=500, detail="Resume prompt template not configured")
    return build_resume_prompt(job, profile, tpl.value)


@router.get("/{job_key}/cover/prompt", response_class=PlainTextResponse)
def get_cover_prompt(job_key: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.job_key == job_key).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    profile = _load_user_profile(db)
    tpl = db.query(Config).filter_by(key="cover_prompt_template").first()
    if not tpl:
        raise HTTPException(status_code=500, detail="Cover prompt template not configured")
    return build_cover_prompt(job, profile, tpl.value)


@router.get("/{job_key}/description/prompt", response_class=PlainTextResponse)
def get_description_prompt(job_key: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.job_key == job_key).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    tpl = db.query(Config).filter_by(key="description_prompt_template").first()
    if not tpl:
        raise HTTPException(status_code=500, detail="Description extraction prompt not configured")
    return build_description_prompt(job, tpl.value)


@router.post("/{job_key}/description/extract")
def extract_description(job_key: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.job_key == job_key).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    tpl = db.query(Config).filter_by(key="description_prompt_template").first()
    if not tpl:
        raise HTTPException(status_code=400, detail="No description extraction prompt configured")
    prompt = build_description_prompt(job, tpl.value)
    client, model = get_openai_client(db)
    job.extraction_md = _call_llm_for_extraction(client, model, prompt)
    db.commit()
    db.refresh(job)
    return _serialize(job)


@router.get("/{job_key}/description", response_class=HTMLResponse)
def serve_description_html(job_key: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.job_key == job_key).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.extraction_md:
        raise HTTPException(status_code=404, detail="No extraction available")
    body = _markdown.markdown(job.extraction_md, extensions=["extra"])
    return HTMLResponse(content=f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  body {{ font-family: system-ui, sans-serif; padding: 1.5rem; line-height: 1.6; color: #e8e8e8; background: #1a1a1a; }}
  h1, h2, h3 {{ color: #fff; margin-top: 1.5rem; }}
  ul {{ padding-left: 1.5rem; }}
  li {{ margin: 0.2rem 0; }}
  strong {{ color: #fff; }}
</style>
</head><body>{body}</body></html>""")


@router.delete("/{job_key}")
def delete_job(job_key: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.job_key == job_key).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    db.delete(job)
    db.commit()
    return {"deleted": job_key}
