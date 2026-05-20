from __future__ import annotations

import html as _html
import json
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
import markdown as _markdown
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
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
    prompts = json.loads(_cfg_val(db, f"{type_}_prompts") or "[]")
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
    templates = json.loads(_cfg_val(db, "latex_templates") or "[]")
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
    import json as _json
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


@router.post("/{job_key}/generate")
def generate_job_endpoint(job_key: str, db: Session = Depends(get_db)):
    job = Job.get(job_key, db)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        _do_generate_resume(job, db)
        _do_generate_cover(job, db)
    except Exception as e:
        print(f"[generator] ERROR for {job_key}: {e}", file=__import__('sys').stderr)
    db.refresh(job)
    _emit(job)
    return job.serialize()


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


@router.post("/{job_key}/generate/resume/md")
def generate_resume_md_endpoint(job_key: str, db: Session = Depends(get_db)):
    job = Job.get(job_key, db)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    prompt = _resolve_prompt(db, "resume")
    try:
        client, model = _get_client_for_named_provider(db, prompt["provider_name"], prompt["model_id"])
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    user = User.load(db)
    try:
        job.generate_resume_md(user, prompt["content"], client, model, db)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Resume markdown generation failed: {exc}")
    db.refresh(job)
    _emit(job)
    return job.serialize()


@router.post("/{job_key}/generate/resume/pdf")
def generate_resume_pdf_endpoint(job_key: str, db: Session = Depends(get_db)):
    job = Job.get(job_key, db)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    md_path = _GENERATOR_OUTPUTS / f"{job_key}_resume.md"
    if not md_path.exists():
        raise HTTPException(status_code=400, detail="Resume markdown must be generated first")
    prompt = _resolve_prompt(db, "resume")
    template_path = _resolve_template(db, prompt.get("template_name", ""))
    try:
        job.generate_resume_pdf(template_path, db)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Resume PDF rendering failed: {exc}")
    db.refresh(job)
    if not job.resume_path:
        raise HTTPException(status_code=500, detail="Resume PDF rendering failed")
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


@router.post("/{job_key}/generate/cover/md")
def generate_cover_md_endpoint(job_key: str, db: Session = Depends(get_db)):
    job = Job.get(job_key, db)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    prompt = _resolve_prompt(db, "cover")
    try:
        client, model = _get_client_for_named_provider(db, prompt["provider_name"], prompt["model_id"])
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    user = User.load(db)
    try:
        job.generate_cover_md(user, prompt["content"], client, model, db)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Cover letter markdown generation failed: {exc}")
    db.refresh(job)
    _emit(job)
    return job.serialize()


@router.post("/{job_key}/generate/cover/pdf")
def generate_cover_pdf_endpoint(job_key: str, db: Session = Depends(get_db)):
    job = Job.get(job_key, db)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.resume_path:
        raise HTTPException(status_code=400, detail="Resume PDF must be generated before cover letter PDF")
    md_path = _GENERATOR_OUTPUTS / f"{job_key}_cover.md"
    if not md_path.exists():
        raise HTTPException(status_code=400, detail="Cover letter markdown must be generated first")
    prompt = _resolve_prompt(db, "cover")
    template_path = _resolve_template(db, prompt.get("template_name", ""))
    try:
        job.generate_cover_pdf(template_path, db)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Cover letter PDF rendering failed: {exc}")
    db.refresh(job)
    if job.cover_path is None:
        raise HTTPException(status_code=500, detail="Cover letter PDF rendering failed")
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


@router.get("/{job_key}/resume/prompt", response_class=PlainTextResponse)
def get_resume_prompt(job_key: str, db: Session = Depends(get_db)):
    job = Job.get(job_key, db)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    user = User.load(db)
    prompt = _resolve_prompt(db, "resume")
    return job.build_resume_prompt(user, prompt["content"], db)


@router.get("/{job_key}/cover/prompt", response_class=PlainTextResponse)
def get_cover_prompt(job_key: str, db: Session = Depends(get_db)):
    job = Job.get(job_key, db)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    user = User.load(db)
    prompt = _resolve_prompt(db, "cover")
    return job.build_cover_prompt(user, prompt["content"], db)


@router.get("/{job_key}/description/prompt", response_class=PlainTextResponse)
def get_description_prompt(job_key: str, db: Session = Depends(get_db)):
    job = Job.get(job_key, db)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    prompt = _resolve_prompt(db, "description")
    return job.build_description_prompt(prompt["content"])


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
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
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


@router.get("/{job_key}/description", response_class=HTMLResponse)
def serve_description_html(job_key: str, view: str = Query("rendered", pattern="^(rendered|json)$"), db: Session = Depends(get_db)):
    job = Job.get(job_key, db)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if not (job.ext_seniority or job.ext_required_skills):
        raise HTTPException(status_code=404, detail="No extraction available")

    _IFRAME_STYLE = """
      body { font-family: system-ui, sans-serif; font-size: 0.85rem; padding: 0.75rem; line-height: 1.6; color: #212529; background: #f8f9fa; margin: 0; }
      h2 { font-size: 0.9rem; color: #212529; margin: 1rem 0 0.25rem; }
      ul { padding-left: 1.25rem; margin: 0.25rem 0; }
      li { margin: 0.1rem 0; }
      strong { color: #212529; }
      pre { white-space: pre-wrap; word-wrap: break-word; margin: 0; }
    """

    body = _markdown.markdown(job._ext_to_markdown(), extensions=["extra"])
    return HTMLResponse(content=f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>{_IFRAME_STYLE}</style></head>
<body>{body}</body></html>""")


@router.delete("/{job_key}")
def delete_job(job_key: str, db: Session = Depends(get_db)):
    job = Job.get(job_key, db)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    db.delete(job)
    db.commit()
    return {"deleted": job_key}
