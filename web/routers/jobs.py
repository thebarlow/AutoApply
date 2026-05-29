from __future__ import annotations

import json as _json
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from core.job import Job, JobState
from core.user import User, PromptNotConfiguredError
from core.llm import get_client_for_profile
from db.database import get_db, Config
from web.sse import send as _sse_send
from web import llm_status

_GENERATOR_DIR = Path(__file__).parent.parent.parent / "generator"
_GENERATOR_OUTPUTS = _GENERATOR_DIR / "outputs"
_RESUME_TEMPLATE = _GENERATOR_DIR / "resume_template.html"
_COVER_TEMPLATE = _GENERATOR_DIR / "cover_template.html"


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


def _get_default_template_name(db: Session) -> str:
    """Return the first configured LaTeX template name; raises HTTP 400 if none."""
    templates = _json.loads(_cfg_val(db, "latex_templates") or "[]")
    if not templates:
        raise HTTPException(
            status_code=400,
            detail="No LaTeX template configured. Upload one under Config.",
        )
    return templates[0]["name"]


router = APIRouter(prefix="/api/jobs")


class StateUpdate(BaseModel):
    state: str


_VALID_STATES = {s.value for s in JobState}

_REVIEW_ACTIONS = {"score", "resume", "cover", "description"}


def _add_pending_review(job: Job, action: str) -> None:
    """Append `action` to job.pending_review_actions (deduped)."""
    cur = _json.loads(job.pending_review_actions or "[]")
    if action not in cur:
        cur.append(action)
    job.pending_review_actions = _json.dumps(cur)


def _remove_pending_review(job: Job, action: str) -> bool:
    """Remove `action` from job.pending_review_actions. Returns True if list is now empty."""
    cur = _json.loads(job.pending_review_actions or "[]")
    cur = [a for a in cur if a != action]
    job.pending_review_actions = _json.dumps(cur)
    return len(cur) == 0


def _emit(job: Job) -> None:
    """Serialize job and push to all SSE clients."""
    _sse_send("job", job.serialize())


def _maybe_start_refinement(job_key: str, doc_type: str, db: Session) -> None:
    """Spawn a background refinement thread if the user profile has it enabled."""
    import threading
    try:
        user = User.load(db)
    except RuntimeError:
        return
    enabled = getattr(user, f"{doc_type}_refine_enabled", True)
    max_turns = int(getattr(user, f"{doc_type}_refine_max_turns", 1))
    if not enabled or max_turns == 0:
        return
    if doc_type == "resume":
        from web.intake_pipeline import run_resume_refinement
        threading.Thread(target=run_resume_refinement, args=(job_key,), daemon=True).start()
    else:
        from web.intake_pipeline import run_cover_refinement
        threading.Thread(target=run_cover_refinement, args=(job_key,), daemon=True).start()


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


class JobFieldsUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    company: str | None = None
    location: str | None = None
    salary: str | None = None
    url: str | None = None


@router.patch("/{job_key}/fields")
def update_job_fields(job_key: str, body: JobFieldsUpdate, db: Session = Depends(get_db)):
    job = Job.get(job_key, db)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    data = body.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(job, key, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A job with that URL already exists")
    db.refresh(job)
    _emit(job)
    return job.serialize()


class FlagUpdate(BaseModel):
    flagged: bool


@router.patch("/{job_key}/flag")
def update_job_flag(job_key: str, body: FlagUpdate, db: Session = Depends(get_db)):
    job = Job.get(job_key, db)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    job.flagged = body.flagged
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
    try:
        prompt_content = user.resolve_prompt("scoring")
    except PromptNotConfiguredError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    try:
        client, model = get_client_for_profile(user, user.prompt_scoring_model)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    config = _load_score_config(db)
    llm_status.start(job_key, "score")
    try:
        job.score(user, config, client, model, db, prompt_content)
        _add_pending_review(job, "score")
        job.unread_indicator = "ok"
        job.last_result_error = None
        db.commit()
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        job = Job.get(job_key, db)
        job.unread_indicator = "error"
        job.last_result_error = str(exc)
        db.commit()
        db.refresh(job)
        _emit(job)
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        llm_status.finish(job_key, "score")
    db.refresh(job)
    _emit(job)
    return job.serialize()


def _do_generate_resume(job: Job, db: Session) -> None:
    """Resolve active resume prompt and generate MD + PDF for job."""
    user = User.load(db)
    try:
        prompt_content = user.resolve_prompt("resume")
    except PromptNotConfiguredError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    try:
        client, model = get_client_for_profile(user, user.prompt_resume_model)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    job.generate_resume_md(user, prompt_content, client, model, db)
    job.generate_resume_pdf(_RESUME_TEMPLATE, db)


def _do_generate_cover(job: Job, db: Session) -> None:
    """Resolve active cover prompt and generate MD + PDF for job."""
    user = User.load(db)
    try:
        prompt_content = user.resolve_prompt("cover")
    except PromptNotConfiguredError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    try:
        client, model = get_client_for_profile(user, user.prompt_cover_model)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    job.generate_cover_md(user, prompt_content, client, model, db)
    job.generate_cover_pdf(_COVER_TEMPLATE, db)


@router.post("/{job_key}/generate/resume")
def generate_resume_endpoint(job_key: str, db: Session = Depends(get_db)):
    job = Job.get(job_key, db)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    llm_status.start(job_key, "resume")
    try:
        _do_generate_resume(job, db)
        _add_pending_review(job, "resume")
        job.unread_indicator = "ok"
        job.last_result_error = None
        db.commit()
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        job = Job.get(job_key, db)
        job.unread_indicator = "error"
        job.last_result_error = str(exc)
        db.commit()
        db.refresh(job)
        _emit(job)
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        llm_status.finish(job_key, "resume")
    db.refresh(job)
    _emit(job)
    # Spawn background refinement loop if enabled
    _maybe_start_refinement(job_key, "resume", db)
    return job.serialize()


@router.post("/{job_key}/generate/cover")
def generate_cover_endpoint(job_key: str, db: Session = Depends(get_db)):
    job = Job.get(job_key, db)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    llm_status.start(job_key, "cover")
    try:
        _do_generate_cover(job, db)
        _add_pending_review(job, "cover")
        job.unread_indicator = "ok"
        job.last_result_error = None
        db.commit()
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        job = Job.get(job_key, db)
        job.unread_indicator = "error"
        job.last_result_error = str(exc)
        db.commit()
        db.refresh(job)
        _emit(job)
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        llm_status.finish(job_key, "cover")
    db.refresh(job)
    _emit(job)
    # Spawn background refinement loop if enabled
    _maybe_start_refinement(job_key, "cover", db)
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


@router.get("/{job_key}/{doc_type}/turn/{n}/markdown", response_class=PlainTextResponse)
def serve_doc_turn_markdown(job_key: str, doc_type: str, n: int, db: Session = Depends(get_db)):
    if doc_type not in ("resume", "cover"):
        raise HTTPException(status_code=400, detail="doc_type must be 'resume' or 'cover'")
    job = Job.get(job_key, db)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    path = _GENERATOR_OUTPUTS / f"{job_key}_{doc_type}_turn_{n}.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Turn {n} snapshot not found")
    return path.read_text(encoding="utf-8")


async def _read_body_text(request: Request) -> str:
    """Read request body as UTF-8 text; bridges async body-reading into sync route handlers."""
    raw = await request.body()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Request body must be valid UTF-8 text")


def _put_document_markdown_sync(
    job_key: str,
    doc_type: str,  # "resume" or "cover"
    content: str,
    db: Session,
):
    job = Job.get(job_key, db)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    suffix = "_resume.md" if doc_type == "resume" else "_cover.md"
    md_path = _GENERATOR_OUTPUTS / f"{job_key}{suffix}"
    md_path.parent.mkdir(parents=True, exist_ok=True)
    old_content = md_path.read_text(encoding="utf-8") if md_path.exists() else None
    md_path.write_text(content, encoding="utf-8")

    try:
        if doc_type == "resume":
            job.generate_resume_pdf(_RESUME_TEMPLATE, db, max_pages=None)
        else:
            job.generate_cover_pdf(_COVER_TEMPLATE, db)
    except Exception as exc:
        if old_content is not None:
            md_path.write_text(old_content, encoding="utf-8")
        else:
            md_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"PDF render failed: {exc}")

    db.commit()
    db.refresh(job)
    _emit(job)
    return job.serialize()


@router.put("/{job_key}/resume/markdown")
def put_resume_markdown(
    job_key: str,
    content: str = Depends(_read_body_text),
    db: Session = Depends(get_db),
):
    return _put_document_markdown_sync(job_key, "resume", content, db)


@router.put("/{job_key}/cover/markdown")
def put_cover_markdown(
    job_key: str,
    content: str = Depends(_read_body_text),
    db: Session = Depends(get_db),
):
    return _put_document_markdown_sync(job_key, "cover", content, db)


def _do_extract_description(job: Job, db: Session) -> None:
    """Run description extraction LLM call and persist structured fields."""
    user = User.load(db)
    try:
        prompt_content = user.resolve_prompt("extraction")
    except PromptNotConfiguredError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    try:
        client, model = get_client_for_profile(user, user.prompt_extraction_model)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    actual_prompt = job.build_description_prompt(prompt_content)
    try:
        raw = _call_llm_for_extraction(client, model, actual_prompt)
    except Exception as exc:
        raise RuntimeError(f"Description extraction failed: {exc}") from exc
    try:
        data = _json.loads(raw)
    except (_json.JSONDecodeError, TypeError):
        raise RuntimeError("Description extraction failed: LLM returned invalid JSON")

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
    salary_min = data.get("salary_min")
    salary_max = data.get("salary_max")
    job.ext_salary_min = float(salary_min) if salary_min is not None else None
    job.ext_salary_max = float(salary_max) if salary_max is not None else None
    _add_pending_review(job, "description")
    job.unread_indicator = "ok"
    job.last_result_error = None
    db.commit()


@router.post("/{job_key}/description/extract")
def extract_description(job_key: str, db: Session = Depends(get_db)):
    job = Job.get(job_key, db)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    llm_status.start(job_key, "description")
    try:
        _do_extract_description(job, db)
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        job = Job.get(job_key, db)
        job.unread_indicator = "error"
        job.last_result_error = str(exc)
        db.commit()
        db.refresh(job)
        _emit(job)
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        llm_status.finish(job_key, "description")
    db.refresh(job)
    _emit(job)
    return job.serialize()


@router.post("/{job_key}/seen")
def mark_job_seen(job_key: str, db: Session = Depends(get_db)):
    job = Job.get(job_key, db)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    job.unread_indicator = None
    job.last_result_error = None
    job.pending_review_actions = "[]"
    db.commit()
    db.refresh(job)
    _emit(job)
    return job.serialize()


@router.post("/{job_key}/seen/{action}")
def mark_job_action_seen(job_key: str, action: str, db: Session = Depends(get_db)):
    if action not in _REVIEW_ACTIONS:
        raise HTTPException(status_code=400, detail=f"Invalid action: {action!r}")
    job = Job.get(job_key, db)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    now_empty = _remove_pending_review(job, action)
    # Only clear the "ok" indicator when nothing is pending. Leave "error" alone.
    if now_empty and job.unread_indicator == "ok":
        job.unread_indicator = None
    db.commit()
    db.refresh(job)
    _emit(job)
    # Delete per-turn refinement snapshots for the dismissed action
    if action in ("resume", "cover"):
        for snap in _GENERATOR_OUTPUTS.glob(f"{job_key}_{action}_turn_*.md"):
            try:
                snap.unlink()
            except OSError:
                pass
    return job.serialize()


@router.delete("/{job_key}")
def delete_job(job_key: str, db: Session = Depends(get_db)):
    job = Job.get(job_key, db)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    job.state = JobState.DELETED.value
    db.commit()
    db.refresh(job)
    _emit(job)
    return job.serialize()
