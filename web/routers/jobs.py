from __future__ import annotations

import json as _json
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.job import Job, JobState
from core.user import User
from core.llm import get_openai_client
from core.llm import get_client_for_named_provider as _get_client_for_named_provider
from db.database import get_db, Config
from web.sse import broadcast as _broadcast

_GENERATOR_OUTPUTS = Path(__file__).parent.parent.parent / "generator" / "outputs"


def _call_llm_for_extraction(client, model: str, prompt: str) -> str:
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    content = response.choices[0].message.content or ""
    content = re.sub(r"^```(?:json)?\s*", "", content.strip(), flags=re.IGNORECASE)
    content = re.sub(r"\s*```$", "", content.strip())
    return content.strip()


def _cfg_val(db: Session, key: str) -> str:
    row = db.query(Config).filter_by(key=key).first()
    return row.value if row else ""


def _resolve_prompt(db: Session, type_: str) -> dict:
    """Return the active prompt dict for a type; raises HTTP 400 if not configured."""
    active_id = _cfg_val(db, f"active_{type_}_prompt_id")
    prompts = _json.loads(_cfg_val(db, f"{type_}_prompts") or "[]")
    prompt = next((p for p in prompts if p["id"] == active_id), None)
    if not prompt:
        raise HTTPException(
            status_code=400,
            detail=f"No active {type_} prompt configured. Set one under Config → Scaffolding.",
        )
    for required_key in ("content", "provider_name", "model_id"):
        if required_key not in prompt:
            raise HTTPException(
                status_code=400,
                detail=f"Active {type_} prompt is missing required field '{required_key}'. Re-save it in Config → Scaffolding.",
            )
    return prompt


def _resolve_template(db: Session, template_name: str) -> Path:
    """Return Path for a named LaTeX template; raises HTTP 400 if not found."""
    if not template_name:
        raise HTTPException(
            status_code=400,
            detail="No LaTeX template assigned to this prompt. Set one under Config → Scaffolding.",
        )
    templates = _json.loads(_cfg_val(db, "latex_templates") or "[]")
    match = next((t for t in templates if t["name"] == template_name), None)
    if not match:
        raise HTTPException(status_code=400, detail=f"LaTeX template '{template_name}' not found.")
    p = Path(match["path"])
    if not p.exists():
        raise HTTPException(status_code=400, detail=f"LaTeX template file missing on disk: {p}")
    return p


router = APIRouter(prefix="/api/jobs")


class StateUpdate(BaseModel):
    state: str


_VALID_STATES = {s.value for s in JobState}


def _emit(job: Job) -> None:
    """Serialize job and push to all SSE clients."""
    _broadcast(_json.dumps(job.serialize()))


@router.get("")
def get_jobs(db: Session = Depends(get_db)):
    jobs = db.query(Job).order_by(Job.final_score.desc()).all()
    return [j.serialize() for j in jobs]


@router.get("/{job_key}")
def get_job(job_key: str, db: Session = Depends(get_db)):
    job = Job.get(job_key, db)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.serialize()


@router.patch("/{job_key}/state")
def update_job_state(job_key: str, body: StateUpdate, db: Session = Depends(get_db)):
    if body.state not in _VALID_STATES:
        raise HTTPException(status_code=400, detail=f"Invalid state: {body.state!r}")

    job = Job.get(job_key, db)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    job.state = body.state
    db.commit()
    db.refresh(job)
    _emit(job)
    return job.serialize()


def _load_score_config(db: Session) -> dict:
    """Load scoring weights from the config table."""
    result = {}
    for key in ("w1", "w2", "auto_reject_threshold", "auto_approve_threshold"):
        row = db.query(Config).filter_by(key=key).first()
        result[key] = float(row.value) if row else 0.5
    return result


@router.post("/{job_key}/score")
def score_job_endpoint(job_key: str, db: Session = Depends(get_db)):
    job = Job.get(job_key, db)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    user = User.load(db)
    config = _load_score_config(db)
    client, model = get_openai_client(db)
    job.score(user, config, client, model, db)
    db.refresh(job)
    _emit(job)
    return job.serialize()


def _do_generate_resume(job: Job, db: Session) -> None:
    """Resolve active resume prompt and generate MD + PDF for job."""
    prompt = _resolve_prompt(db, "resume")
    client, model = _get_client_for_named_provider(db, prompt["provider_name"], prompt["model_id"])
    user = User.load(db)
    job.generate_resume_md(user, prompt["content"], client, model, db)
    template_path = _resolve_template(db, prompt.get("template_name", ""))
    job.generate_resume_pdf(template_path, db)


def _do_generate_cover(job: Job, db: Session) -> None:
    """Resolve active cover prompt and generate MD + PDF for job."""
    prompt = _resolve_prompt(db, "cover")
    client, model = _get_client_for_named_provider(db, prompt["provider_name"], prompt["model_id"])
    user = User.load(db)
    job.generate_cover_md(user, prompt["content"], client, model, db)
    template_path = _resolve_template(db, prompt.get("template_name", ""))
    job.generate_cover_pdf(template_path, db)


@router.post("/{job_key}/generate/resume")
def generate_resume_endpoint(job_key: str, db: Session = Depends(get_db)):
    job = Job.get(job_key, db)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        _do_generate_resume(job, db)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    db.refresh(job)
    _emit(job)
    return job.serialize()


@router.post("/{job_key}/generate/cover")
def generate_cover_endpoint(job_key: str, db: Session = Depends(get_db)):
    job = Job.get(job_key, db)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        _do_generate_cover(job, db)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    db.refresh(job)
    _emit(job)
    return job.serialize()


@router.get("/{job_key}/resume")
def serve_resume(job_key: str, db: Session = Depends(get_db)):
    job = Job.get(job_key, db)
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
    job = Job.get(job_key, db)
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
    job = Job.get(job_key, db)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    path = _GENERATOR_OUTPUTS / f"{job_key}_resume.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Resume markdown not found")
    return path.read_text(encoding="utf-8")


@router.get("/{job_key}/cover/markdown", response_class=PlainTextResponse)
def serve_cover_markdown(job_key: str, db: Session = Depends(get_db)):
    job = Job.get(job_key, db)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    path = _GENERATOR_OUTPUTS / f"{job_key}_cover.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Cover letter markdown not found")
    return path.read_text(encoding="utf-8")


@router.post("/{job_key}/description/extract")
def extract_description(job_key: str, db: Session = Depends(get_db)):
    job = Job.get(job_key, db)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    prompt = _resolve_prompt(db, "description")
    actual_prompt = job.build_description_prompt(prompt["content"])
    try:
        client, model = _get_client_for_named_provider(db, prompt["provider_name"], prompt["model_id"])
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    try:
        raw = _call_llm_for_extraction(client, model, actual_prompt)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Description extraction failed: {exc}")
    # Parse and store into ext_* columns via job method
    try:
        data = _json.loads(raw)
    except (_json.JSONDecodeError, TypeError):
        raise HTTPException(status_code=500, detail="Description extraction failed: LLM returned invalid JSON")
    job.ext_seniority = data.get("seniority", "")
    job.ext_role_type = data.get("role_type", "")
    job.ext_domain = data.get("domain", "")
    job.ext_work_arrangement = data.get("work_arrangement", "")
    job.ext_employment_type = data.get("employment_type", "")
    job.ext_required_skills = ", ".join(data.get("required_skills") or [])
    job.ext_preferred_skills = ", ".join(data.get("preferred_skills") or [])
    job.ext_tech_stack = ", ".join(data.get("tech_stack") or [])
    job.ext_key_responsibilities = ", ".join(data.get("key_responsibilities") or [])
    job.ext_company_signals = ", ".join(data.get("company_signals") or [])
    db.commit()
    db.refresh(job)
    _emit(job)
    return job.serialize()


@router.delete("/{job_key}")
def delete_job(job_key: str, db: Session = Depends(get_db)):
    job = Job.get(job_key, db)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    db.delete(job)
    db.commit()
    return {"deleted": job_key}
