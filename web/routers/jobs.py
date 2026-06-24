from __future__ import annotations

import json as _json
import re
from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from core.job import Job, JobState
from core.user import User, PromptNotConfiguredError
from core.llm import get_client_for_profile
from core.schemas import ResumeDocument, CoverDocument
from core.document_assembler import (
    resume_section_order,
    assemble_resume_markdown,
    assemble_cover_markdown,
)
from core.document_parser import (
    reconstruct_resume_document_from_markdown,
    reconstruct_cover_document_from_markdown,
)
from db.database import get_db, Config, Document
from core.metering import meter_action
from core.credits import InsufficientCredits
from web.sse import send as _sse_send
from web.tenancy import current_profile_id, scoped
from web import llm_status

def _spawn(target, *args) -> None:
    """Start a fire-and-forget daemon thread.

    Centralized so tests can disable background work (the suite patches this to a
    no-op to avoid lingering gate threads); production always spawns.
    """
    import threading
    threading.Thread(target=target, args=args, daemon=True).start()


_GENERATOR_DIR = Path(__file__).parent.parent.parent / "generator"
_GENERATOR_OUTPUTS = _GENERATOR_DIR / "outputs"
_OUTPUTS_DIR = _GENERATOR_OUTPUTS  # alias used by backfill logic (tests monkeypatch this name)
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


def _maybe_start_refinement(job_key: str, doc_type: str, db: Session, profile_id: int) -> None:
    """Spawn a background refinement thread if the user profile has it enabled."""
    import threading
    try:
        user = User.load(db, profile_id=profile_id)
    except RuntimeError:
        return
    enabled = getattr(user, f"{doc_type}_refine_enabled", True)
    max_turns = int(getattr(user, f"{doc_type}_refine_max_turns", 1))
    if not enabled or max_turns == 0:
        return
    if doc_type == "resume":
        from web.intake_pipeline import run_resume_refinement
        threading.Thread(target=run_resume_refinement, args=(job_key, profile_id), daemon=True).start()
    else:
        from web.intake_pipeline import run_cover_refinement
        threading.Thread(target=run_cover_refinement, args=(job_key, profile_id), daemon=True).start()


@router.get("")
def get_jobs(db: Session = Depends(get_db), profile_id: int = Depends(current_profile_id)):
    jobs = scoped(db, Job, profile_id).order_by(Job.final_score.desc()).all()
    return [j.serialize() for j in jobs]


@router.get("/{job_key}")
def get_job(job_key: str, db: Session = Depends(get_db), profile_id: int = Depends(current_profile_id)):
    job = Job.get(job_key, db, profile_id=profile_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.serialize()


@router.patch("/{job_key}/state")
def update_job_state(
    job_key: str,
    body: StateUpdate,
    db: Session = Depends(get_db),
    profile_id: int = Depends(current_profile_id),
):
    if body.state not in _VALID_STATES:
        raise HTTPException(status_code=400, detail=f"Invalid state: {body.state!r}")

    job = Job.get(job_key, db, profile_id=profile_id)
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
def update_job_fields(
    job_key: str,
    body: JobFieldsUpdate,
    db: Session = Depends(get_db),
    profile_id: int = Depends(current_profile_id),
):
    job = Job.get(job_key, db, profile_id=profile_id)
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


class FeedbackNote(BaseModel):
    section: str = ""
    label: str = ""
    note: str = ""


class FeedbackRequest(BaseModel):
    notes: list[FeedbackNote]


@router.patch("/{job_key}/flag")
def update_job_flag(
    job_key: str,
    body: FlagUpdate,
    db: Session = Depends(get_db),
    profile_id: int = Depends(current_profile_id),
):
    job = Job.get(job_key, db, profile_id=profile_id)
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
def score_job_endpoint(
    job_key: str,
    db: Session = Depends(get_db),
    profile_id: int = Depends(current_profile_id),
):
    job = Job.get(job_key, db, profile_id=profile_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    user = User.load(db, profile_id=profile_id)
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
        with meter_action(db, profile_id, action="score", job_key=job.job_key):
            job.score(user, config, client, model, db, prompt_content)
        _add_pending_review(job, "score")
        job.unread_indicator = "ok"
        job.last_result_error = None
        db.commit()
    except (HTTPException, InsufficientCredits):
        raise
    except Exception as exc:
        db.rollback()
        job = Job.get(job_key, db, profile_id=profile_id)
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


def _do_generate_resume(job: Job, db: Session, profile_id: int) -> None:
    """Resolve active resume prompt and generate MD + PDF for job."""
    user = User.load(db, profile_id=profile_id)
    try:
        prompt_content = user.resolve_prompt("resume")
    except PromptNotConfiguredError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    try:
        client, model = get_client_for_profile(user, user.prompt_resume_model)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    with meter_action(db, profile_id, action="generate", job_key=job.job_key):
        job.generate_resume_md(user, prompt_content, client, model, db)
    job.generate_resume_pdf(_RESUME_TEMPLATE, db)


def _do_generate_cover(job: Job, db: Session, profile_id: int) -> None:
    """Resolve active cover prompt and generate MD + PDF for job."""
    user = User.load(db, profile_id=profile_id)
    try:
        prompt_content = user.resolve_prompt("cover")
    except PromptNotConfiguredError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    try:
        client, model = get_client_for_profile(user, user.prompt_cover_model)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    with meter_action(db, profile_id, action="generate", job_key=job.job_key):
        job.generate_cover_md(user, prompt_content, client, model, db)
    job.generate_cover_pdf(_COVER_TEMPLATE, db)


@router.post("/{job_key}/generate/resume")
def generate_resume_endpoint(
    job_key: str,
    db: Session = Depends(get_db),
    profile_id: int = Depends(current_profile_id),
):
    job = Job.get(job_key, db, profile_id=profile_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    llm_status.start(job_key, "resume")
    try:
        _do_generate_resume(job, db, profile_id)
        _add_pending_review(job, "resume")
        job.unread_indicator = "ok"
        job.last_result_error = None
        db.commit()
    except (HTTPException, InsufficientCredits):
        raise
    except Exception as exc:
        db.rollback()
        job = Job.get(job_key, db, profile_id=profile_id)
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
    # Always run the résumé post-process in the background: refinement (if
    # enabled) followed by the ATS gate. When refinement is off/0 turns the
    # refine step is a no-op and the gate still runs right after generation.
    from web.intake_pipeline import run_resume_refinement
    _spawn(run_resume_refinement, job_key, profile_id)
    return job.serialize()


@router.post("/{job_key}/generate/cover")
def generate_cover_endpoint(
    job_key: str,
    db: Session = Depends(get_db),
    profile_id: int = Depends(current_profile_id),
):
    job = Job.get(job_key, db, profile_id=profile_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    llm_status.start(job_key, "cover")
    try:
        _do_generate_cover(job, db, profile_id)
        _add_pending_review(job, "cover")
        job.unread_indicator = "ok"
        job.last_result_error = None
        db.commit()
    except (HTTPException, InsufficientCredits):
        raise
    except Exception as exc:
        db.rollback()
        job = Job.get(job_key, db, profile_id=profile_id)
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
    _maybe_start_refinement(job_key, "cover", db, profile_id)
    return job.serialize()


@router.post("/{job_key}/{doc_type}/feedback", status_code=202)
def submit_document_feedback(
    job_key: str,
    doc_type: str,
    payload: FeedbackRequest,
    db: Session = Depends(get_db),
    profile_id: int = Depends(current_profile_id),
):
    """Apply user section-anchored feedback to a generated document (one-shot).

    Spawns a background refine using the existing refine path. Returns 202 with
    the current job; results stream in over SSE as the refine completes.
    """
    if doc_type not in ("resume", "cover"):
        raise HTTPException(status_code=400, detail="Invalid document type")
    job = Job.get(job_key, db, profile_id=profile_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    # The refine mutates and re-persists the structured doc, so it needs a row to
    # patch. Backfill-and-persist from the on-disk .md when the job was only ever
    # viewed (parse-on-read leaves no row); 404 only when there's nothing to refine.
    if not _ensure_document_row(db, job_key, doc_type, profile_id):
        raise HTTPException(status_code=404, detail=f"No {doc_type} document to refine")
    notes = [n.model_dump() for n in payload.notes if (n.note or "").strip()]
    if not notes:
        raise HTTPException(status_code=400, detail="No feedback provided")
    from web.intake_pipeline import run_user_feedback_refine
    _spawn(run_user_feedback_refine, job_key, doc_type, notes, profile_id)
    return job.serialize()


@router.get("/{job_key}/resume")
def serve_resume(job_key: str, db: Session = Depends(get_db), profile_id: int = Depends(current_profile_id)):
    job = Job.get(job_key, db, profile_id=profile_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.resume_path:
        raise HTTPException(status_code=404, detail="Resume not found")
    path = Path(job.resume_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Resume file missing")
    return FileResponse(path, media_type="application/pdf")


@router.get("/{job_key}/cover")
def serve_cover(job_key: str, db: Session = Depends(get_db), profile_id: int = Depends(current_profile_id)):
    job = Job.get(job_key, db, profile_id=profile_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.cover_path:
        raise HTTPException(status_code=404, detail="Cover letter not found")
    path = Path(job.cover_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Cover letter file missing")
    return FileResponse(path, media_type="application/pdf")


@router.get("/{job_key}/resume/markdown", response_class=PlainTextResponse)
def serve_resume_markdown(job_key: str, db: Session = Depends(get_db), profile_id: int = Depends(current_profile_id)):
    job = Job.get(job_key, db, profile_id=profile_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    path = _GENERATOR_OUTPUTS / f"{job_key}_resume.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Resume markdown not found")
    return path.read_text(encoding="utf-8")


@router.get("/{job_key}/cover/markdown", response_class=PlainTextResponse)
def serve_cover_markdown(job_key: str, db: Session = Depends(get_db), profile_id: int = Depends(current_profile_id)):
    job = Job.get(job_key, db, profile_id=profile_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    path = _GENERATOR_OUTPUTS / f"{job_key}_cover.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Cover letter markdown not found")
    return path.read_text(encoding="utf-8")


@router.get("/{job_key}/{doc_type}/turn/{n}/markdown", response_class=PlainTextResponse)
def serve_doc_turn_markdown(
    job_key: str,
    doc_type: str,
    n: int,
    db: Session = Depends(get_db),
    profile_id: int = Depends(current_profile_id),
):
    if doc_type not in ("resume", "cover"):
        raise HTTPException(status_code=400, detail="doc_type must be 'resume' or 'cover'")
    job = Job.get(job_key, db, profile_id=profile_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    path = _GENERATOR_OUTPUTS / f"{job_key}_{doc_type}_turn_{n}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Turn {n} snapshot not found")
    raw = path.read_text(encoding="utf-8")
    try:
        if doc_type == "resume":
            from core.resume_document_io import is_tree_v1, deserialize_document_tree
            from core.tree_assembler import assemble_resume_tree_markdown
            if is_tree_v1(raw):
                return assemble_resume_tree_markdown(deserialize_document_tree(raw))
            return assemble_resume_markdown(ResumeDocument.model_validate_json(raw))
        return assemble_cover_markdown(CoverDocument.model_validate_json(raw))
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=f"Snapshot schema mismatch: {exc}") from exc


def _doc_model(doc_type: str) -> type[ResumeDocument] | type[CoverDocument]:
    return ResumeDocument if doc_type == "resume" else CoverDocument


def _ensure_document_row(db: Session, job_key: str, doc_type: str, profile_id: int) -> bool:
    """Ensure a structured ``documents`` row exists, persisting one from the on-disk
    ``.md`` if it's missing (the inverse of ``get_document``'s parse-on-read).

    Used before a refine, which needs a row to patch and re-persist. Unlike
    ``get_document`` this intentionally writes the row.

    Returns:
        True if a row exists afterward; False if there was nothing to reconstruct.
    """
    if Document.fetch(db, job_key, doc_type, profile_id=profile_id) is not None:
        return True
    md_path = _OUTPUTS_DIR / f"{job_key}_{doc_type}.md"
    if not md_path.exists():
        return False
    md = md_path.read_text(encoding="utf-8")
    doc = (
        reconstruct_resume_document_from_markdown(md)
        if doc_type == "resume"
        else reconstruct_cover_document_from_markdown(md)
    )
    Document.upsert(db, job_key, doc_type, doc.model_dump_json(), profile_id=profile_id)
    return True


@router.get("/{job_key}/{doc_type}/document")
def get_document(
    job_key: str,
    doc_type: str,
    db: Session = Depends(get_db),
    profile_id: int = Depends(current_profile_id),
):
    if doc_type not in ("resume", "cover"):
        raise HTTPException(status_code=400, detail="doc_type must be 'resume' or 'cover'")
    # Explicit job-existence check mirrors put_document: distinguishes "job missing" (404) from "document missing" (404 below).
    if Job.get(job_key, db, profile_id=profile_id) is None:
        raise HTTPException(status_code=404, detail="Job not found")
    row = Document.fetch(db, job_key, doc_type, profile_id=profile_id)
    if row is None:
        # No structured row: reconstruct from the on-disk .md on every read rather
        # than persisting. Persisting would let a best-effort (lossy) parse shadow
        # the authoritative .md and freeze it against later parser improvements; a
        # real row is created only when the user edits (PUT) or regenerates.
        md_path = _OUTPUTS_DIR / f"{job_key}_{doc_type}.md"
        if md_path.exists():
            md = md_path.read_text(encoding="utf-8")
            doc = (
                reconstruct_resume_document_from_markdown(md)
                if doc_type == "resume"
                else reconstruct_cover_document_from_markdown(md)
            )
            return _json.loads(doc.model_dump_json())
        raise HTTPException(status_code=404, detail="Document not found")
    return _json.loads(row.structured_json)


@router.put("/{job_key}/{doc_type}/document")
def put_document(
    job_key: str,
    doc_type: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    profile_id: int = Depends(current_profile_id),
):
    if doc_type not in ("resume", "cover"):
        raise HTTPException(status_code=400, detail="doc_type must be 'resume' or 'cover'")
    job = Job.get(job_key, db, profile_id=profile_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if doc_type == "resume" and payload.get("schema") == "tree-v1":
        from core.resume_document_io import deserialize_document_tree, serialize_document_tree
        import json as _json2
        try:
            root = deserialize_document_tree(_json2.dumps(payload))
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid document: {exc}")
        serialized = serialize_document_tree(root)
        Document.upsert(db, job_key, "resume", serialized, profile_id=profile_id)
        try:
            job.write_resume_markdown(root)
            job.generate_resume_pdf(_RESUME_TEMPLATE, db, max_pages=1)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"PDF render failed: {exc}")
        db.refresh(job)
        _emit(job)
        from web.intake_pipeline import run_ats_gate
        _spawn(run_ats_gate, job_key, profile_id)
        return _json.loads(serialized)

    try:
        doc = _doc_model(doc_type).model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid document: {exc}")

    if doc_type == "resume":
        doc.section_order = resume_section_order(doc)

    Document.upsert(db, job_key, doc_type, doc.model_dump_json(), profile_id=profile_id)

    try:
        if doc_type == "resume":
            job.write_resume_markdown(doc)
            job.generate_resume_pdf(_RESUME_TEMPLATE, db, max_pages=1)
        else:
            job.write_cover_markdown(doc)
            job.generate_cover_pdf(_COVER_TEMPLATE, db)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PDF render failed: {exc}")

    db.refresh(job)
    _emit(job)
    # A manual résumé edit re-rendered the PDF, invalidating any prior ATS
    # report; re-run the gate in the background so the stored report stays fresh.
    if doc_type == "resume":
        from web.intake_pipeline import run_ats_gate
        _spawn(run_ats_gate, job_key, profile_id)
    return doc.model_dump()


def _do_extract_description(job: Job, db: Session, profile_id: int) -> None:
    """Run description extraction LLM call and persist structured fields."""
    user = User.load(db, profile_id=profile_id)
    try:
        prompt_content = user.resolve_prompt("extraction")
    except PromptNotConfiguredError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    try:
        client, model = get_client_for_profile(user, user.prompt_extraction_model)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    actual_prompt = job.build_description_prompt(prompt_content)
    with meter_action(db, profile_id, action="extract", job_key=job.job_key):
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
def extract_description(
    job_key: str,
    db: Session = Depends(get_db),
    profile_id: int = Depends(current_profile_id),
):
    job = Job.get(job_key, db, profile_id=profile_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    llm_status.start(job_key, "description")
    try:
        _do_extract_description(job, db, profile_id)
    except (HTTPException, InsufficientCredits):
        raise
    except Exception as exc:
        db.rollback()
        job = Job.get(job_key, db, profile_id=profile_id)
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
def mark_job_seen(
    job_key: str,
    db: Session = Depends(get_db),
    profile_id: int = Depends(current_profile_id),
):
    job = Job.get(job_key, db, profile_id=profile_id)
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
def mark_job_action_seen(
    job_key: str,
    action: str,
    db: Session = Depends(get_db),
    profile_id: int = Depends(current_profile_id),
):
    if action not in _REVIEW_ACTIONS:
        raise HTTPException(status_code=400, detail=f"Invalid action: {action!r}")
    job = Job.get(job_key, db, profile_id=profile_id)
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
        for snap in _GENERATOR_OUTPUTS.glob(f"{job_key}_{action}_turn_*.json"):
            try:
                snap.unlink()
            except OSError:
                pass
    return job.serialize()


@router.delete("/{job_key}")
def delete_job(
    job_key: str,
    db: Session = Depends(get_db),
    profile_id: int = Depends(current_profile_id),
):
    job = Job.get(job_key, db, profile_id=profile_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    job.state = JobState.DELETED.value
    db.commit()
    db.refresh(job)
    _emit(job)
    return job.serialize()
