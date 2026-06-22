"""Dev-only, admin-gated comparison harness: Model 1 (single-call) vs Model 2
(per-section) résumé generation. Runs both dry (no persistence, no metering, no
ATS) and returns both Markdowns + eval scores for side-by-side review.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core.document_assembler import assemble_resume_markdown
from core.document_builder import build_resume_document
from core.job import Job, _apply_template, _llm_json_with_retry
from core.llm import get_client_for_profile
from core.profile_tree import resolve_profile_tokens
from core.schemas import ResumeGeneration
from core.section_generator import generate_resume_by_section
from core.document_tree import build_resume_document_tree
from core.tree_assembler import assemble_resume_tree_markdown
from core.user import User
from db.database import get_db
from web.routers.credits import require_admin
from web.tenancy import current_profile_id

router = APIRouter()


def _model1_markdown(job: Job, user: Any, client: Any, model: str, db: Session) -> str:
    """Model 1 (single-call) résumé Markdown, dry — no Document.upsert, no file write."""
    prompt = job.build_resume_prompt(user, user.resolve_prompt("resume"), db)
    generation = _llm_json_with_retry(
        prompt, client, model, ResumeGeneration, max_tokens=16384,
        empty_msg="Model 1 returned empty content.",
    )
    doc = build_resume_document(user, generation, db)
    return assemble_resume_markdown(doc)


def _model2_markdown(job: Job, user: Any, client: Any, model: str, db: Session) -> str:
    """Model 2 (per-section) résumé Markdown via the schema-driven generator.

    Section/item prompts may inject ``{job.*}`` and ``{profile.*}`` tokens; both
    are resolved against this job and the live profile tree before each call.
    """
    root = user.profile_tree_root()
    prompt = job.build_resume_prompt(user, "{job.extracted_description}", db)

    def resolve(text: str) -> str:
        text = resolve_profile_tokens(root, text)
        return _apply_template(text, {"job": job})

    authored = generate_resume_by_section(root, prompt, client, model, resolve=resolve)
    doc_tree = build_resume_document_tree(root, authored)
    return assemble_resume_tree_markdown(doc_tree)


def _one_model(fn, job, user, client, model, eval_prompt, db) -> dict:
    """Run one model's markdown fn + eval; capture failures per-model."""
    try:
        md = fn(job, user, client, model, db)
    except Exception as exc:  # noqa: BLE001 — surface to the page, never 500 the pair
        return {"error": str(exc)}
    result = {"markdown": md}
    result.update(job.evaluate_resume_body(md, eval_prompt, user, client, model))
    return result


def run_comparison(job, user, client, model, eval_prompt, db) -> dict:
    """Run both models independently and return both results."""
    return {
        "model1": _one_model(_model1_markdown, job, user, client, model, eval_prompt, db),
        "model2": _one_model(_model2_markdown, job, user, client, model, eval_prompt, db),
    }


@router.post("/api/dev/resume-compare/{job_key}")
def resume_compare(
    job_key: str,
    db: Session = Depends(get_db),
    profile_id: int = Depends(current_profile_id),
    _admin=Depends(require_admin),
):
    """Generate the résumé both ways for ``job_key`` and return both + eval scores."""
    job = Job.get(job_key, db, profile_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if not job.ext_seniority:
        raise HTTPException(
            status_code=400,
            detail="job has not been extracted yet; run extraction before using the compare harness",
        )
    user = User.load(db, profile_id=profile_id)
    client, model = get_client_for_profile(user, user.prompt_resume_model)
    eval_prompt = user.resolve_prompt("resume_eval")
    return run_comparison(job, user, client, model, eval_prompt, db)
