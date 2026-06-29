"""Dev-only, admin-gated comparison harness: Model 1 (single-call) vs Model 2
(per-section) résumé generation. Runs both dry (no persistence, no metering, no
ATS) and returns both Markdowns + eval scores for side-by-side review.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core.document_assembler import assemble_resume_markdown
from core.utils import markdown_to_html
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

_RESUME_CSS = Path(__file__).resolve().parents[2] / "generator" / "resume.css"

_H2_RE = re.compile(r"<h2\b", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


def _split_sections_html(html: str) -> list[dict]:
    """Split a pandoc HTML fragment into top-level sections at ``<h2>`` boundaries.

    Content preceding the first ``<h2>`` (e.g. a tree-v1 name ``<h1>`` and contact
    ``<p>``) is returned as a leading ``"Header"`` section.

    Args:
        html: The HTML fragment to split.

    Returns:
        Ordered list of ``{"heading": str, "html": str}`` dicts. Empty input
        yields ``[]``.
    """
    if not html or not html.strip():
        return []

    # Indices where each <h2 begins; everything before the first is the header.
    starts = [m.start() for m in _H2_RE.finditer(html)]
    sections: list[dict] = []

    if not starts:
        return [{"heading": "Header", "html": html.strip()}]

    header = html[: starts[0]].strip()
    if header:
        sections.append({"heading": "Header", "html": header})

    bounds = starts + [len(html)]
    for i in range(len(starts)):
        chunk = html[bounds[i] : bounds[i + 1]].strip()
        # Heading text = inner text of the opening <h2>...</h2>.
        end = chunk.lower().find("</h2>")
        open_tag_end = chunk.find(">")
        heading = (
            _TAG_RE.sub("", chunk[open_tag_end + 1 : end]).strip()
            if end != -1 and open_tag_end != -1
            else "Section"
        )
        sections.append({"heading": heading, "html": chunk})

    return sections


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
    result = {"markdown": md, "sections": _split_sections_html(markdown_to_html(md))}
    result.update(job.evaluate_resume_body(md, eval_prompt, user, client, model))
    return result


def run_comparison(job, user, client, model, eval_prompt, db) -> dict:
    """Run both models independently and return both results plus the résumé CSS."""
    css = _RESUME_CSS.read_text(encoding="utf-8") if _RESUME_CSS.exists() else ""
    return {
        "css": css,
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
