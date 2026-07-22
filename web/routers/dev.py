"""Dev-only, admin-gated comparison harness: Model 1 (single-call) vs Model 2
(per-section) résumé generation. Runs both dry (no persistence, no metering, no
ATS) and returns both Markdowns + eval scores for side-by-side review.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import Account

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
from web.routers.credits import require_real_admin
from web.tenancy import current_profile_id

router = APIRouter()


_DEFAULT_LOGIN_EMAIL = "barlowmatt96@gmail.com"


@router.post("/api/dev/login")
def dev_login(request: Request, db: Session = Depends(get_db)):
    """Establish a session for local E2E without OAuth.

    Refuses to run in production (where OAuth is mandatory), by setting the same
    ``session["account_id"]`` a real OAuth callback would. Mirrors the tenancy
    seam's "no login needed outside production" stance for the identity gate
    (``/api/me``), which — unlike ``current_profile_id`` — has no dev bypass.

    Account resolution, in order:

    1. The account whose email matches ``E2E_LOGIN_EMAIL`` (default the owner's
       personal address) — so a normal run against the real local DB logs in as
       *you*, not some other seeded row.
    2. Falls back to the admin account, then the lowest-id account, when that
       email isn't present (e.g. the seeded worktree DB).
    3. **Empty DB** (the ``new-user-test`` clean slate has no account at all):
       provision a throwaway account on a fresh empty profile, so the onboarding
       flow can be driven from its real authed-but-profile-less entry state.
    """
    if os.getenv("APP_ENV") == "production":
        raise HTTPException(status_code=404)

    target = os.getenv("E2E_LOGIN_EMAIL", _DEFAULT_LOGIN_EMAIL).lower()
    acct = (
        db.query(Account).filter(Account.email.ilike(target)).first()
        or db.query(Account).filter_by(is_admin=True).first()
        or db.query(Account).order_by(Account.id).first()
    )
    if acct is None:
        acct = _provision_throwaway_account(db, target)

    request.session["account_id"] = acct.id
    return {"account_id": acct.id, "profile_id": acct.profile_id, "email": acct.email}


class SeedAtsJobBody(BaseModel):
    job_key: str
    apply_url: str
    ats_type: str


@router.post("/api/dev/seed-ats-job")
def seed_ats_job(
    body: SeedAtsJobBody,
    db: Session = Depends(get_db),
    profile_id: int = Depends(current_profile_id),
):
    """Upsert a staged ATS job for the extension autofill harness (non-prod only).

    The extension matches an ATS apply page to a staged job by URL, then POSTs the
    plan request keyed by ``job_key``; both need a persisted row on this profile.
    Idempotent so the harness can re-run without piling up rows.

    Note: the interface spec's ``state="scraped"`` has no matching ``JobState``
    member (the enum only has NEW/PENDING_REVIEW/READY/APPLIED/CONTACT/REJECTED/
    DELETED); ``Job.state`` is an unconstrained String column, so the literal is
    used directly.
    """
    if os.getenv("APP_ENV") == "production":
        raise HTTPException(status_code=404)

    job = Job.get(body.job_key, db, profile_id)
    if job is None:
        job = Job(
            job_key=body.job_key,
            profile_id=profile_id,
            source="dev-seed",
            url=body.apply_url,
        )
        db.add(job)
    job.title = job.title or "E2E ATS Fixture"
    job.company = job.company or "Acme"
    job.state = "scraped"
    job.apply_url_raw = body.apply_url
    job.apply_url_resolved = body.apply_url
    job.ats_type = body.ats_type
    db.commit()
    return {"job_key": body.job_key, "profile_id": profile_id}


def _provision_throwaway_account(db: Session, email: str) -> Account:
    """Create an account on a fresh empty profile for the clean new-user DB.

    Reuses the OAuth path's ``_provision_profile`` (empty ``User`` + seeded
    prompt/alias rows) so the resulting state matches a real first login: an
    authed session whose profile has no data yet, which is exactly what triggers
    the onboarding modal. No Identity row is needed — dev-login sets the session
    by account id directly.
    """
    from datetime import datetime, timezone
    from web.auth.identity import _provision_profile

    profile_id = _provision_profile(db)
    acct = Account(
        email=email,
        is_admin=False,
        profile_id=profile_id,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    db.add(acct)
    db.commit()
    return acct


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


# Baseline single-call prompt (the original full-contract resume prompt). Kept
# inline so the live "resume" slot can be repurposed as the lean per-section job
# context without losing the Model-1 comparison baseline.
_MODEL1_PROMPT = """You are tailoring a one-page resume for a job application. You write ONLY tailored prose; the applicant's contact info, job titles, dates, education, and project names are fixed facts supplied below and must not be invented or altered.

# Applicant Details
Hero: {user.hero}
Skills: {user.skills}

Work Experience (each line is `[index] title at company (dates): summary`):
{user_profile.work_history_indexed}

Projects (each line is `[index] name: description (url)`):
{user_profile.projects_indexed}

# Job Posting
Title: {job.title}
Company: {job.company}
Location: {job.location}
Description:
{job.description}

# Output contract
Return ONLY a single JSON object (no code fences, no commentary) with exactly these keys:

{
  "profile_summary": "<markdown, max 500 chars>",
  "experience": [ {"ref": <work index>, "description": "<markdown bullets>"} ],
  "projects":   [ {"ref": <project index>, "description": "<markdown>"} ],
  "skills":     [ {"category": "<name>", "items": ["<skill>", ...]} ]
}

Rules:
- `experience`: include an object for EACH work index above, keyed by its `ref`. Max 2 bullets per entry, each bullet max 120 chars. Stress skills/responsibilities named in the job description. Do not reorder, rename, or invent entries — refer to them only by `ref`.
- `projects`: SELECT the 2–4 most relevant projects and order them most-relevant-first. Reference each by its `ref`. Each description: max 120 chars, one sentence, no bullets. Omit irrelevant projects (do not include them).
- `skills`: group into at most 6 categories (e.g. Languages, Frameworks, Tools); include only categories with 2+ relevant skills; list job-mentioned skills first.
- `profile_summary`: lead with the candidate's identity for THIS role (nature, scale, stakes of their actual work), then weave in the role's keywords.
- Never imply a title, level, ownership, or outcome the applicant details do not support.
- Use ONLY the supplied indices. Do not invent a `ref` that is not listed above.
"""


def _model1_markdown(job: Job, user: Any, client: Any, model: str, db: Session) -> str:
    """Model 1 (single-call) résumé Markdown, dry — no Document.upsert, no file write."""
    prompt = job.build_resume_prompt(user, _MODEL1_PROMPT, db)
    generation = _llm_json_with_retry(
        prompt, client, model, ResumeGeneration, max_tokens=16384,
        empty_msg="Model 1 returned empty content.",
    )
    doc = build_resume_document(user, generation, db)
    return assemble_resume_markdown(doc)


def _model2_markdown(job: Job, user: Any, client: Any, model: str, db: Session) -> str:
    """Model 2 (per-section) résumé Markdown via the schema-driven generator.

    Mirrors the live path: the lean ``resume`` prompt slot (analyzed job + skill
    inventory) is the shared job context. Section/item prompts may inject
    ``{job.*}`` / ``{profile.*}`` tokens, resolved before each call.
    """
    root = user.profile_tree_root()
    prompt = job.build_resume_prompt(user, user.resolve_prompt("resume"), db)

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
    _admin=Depends(require_real_admin),
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
