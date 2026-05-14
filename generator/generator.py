from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from core.llm import get_openai_client, get_client_for_named_provider
from core.types import JobState, UserProfile, WorkHistoryEntry, EducationEntry, ProjectEntry
from db.database import SessionLocal
from db.models import Config, Job, UserProfileModel

_GENERATOR_DIR = Path(__file__).parent
_OUTPUTS_DIR = _GENERATOR_DIR / "outputs"
_DEFAULT_RESUME_TEMPLATE = _GENERATOR_DIR / "resume_template.tex"
_DEFAULT_COVER_TEMPLATE = _GENERATOR_DIR / "cover_template.tex"


def _render_profile(profile: UserProfile) -> str:
    work = "\n".join(
        f"- {e.title} at {e.company} ({e.start}–{e.end}): {e.summary}"
        for e in profile.work_history
    )
    education = "\n".join(
        f"- {e.degree} in {e.field} from {e.institution} ({e.graduated}), GPA {e.gpa}"
        for e in profile.education
    )
    projects = "\n".join(
        f"- {e.name}: {e.description}"
        + (f" ({e.url})" if e.url else "")
        + (f" — {', '.join(e.technologies)}" if e.technologies else "")
        for e in profile.projects
    )
    return (
        f"Name: {profile.name}\n"
        f"Target roles: {', '.join(profile.target_roles)}\n"
        f"Target salary: ${profile.target_salary_min}–${profile.target_salary_max}\n"
        f"Skills: {', '.join(profile.skills)}\n\n"
        f"Work History:\n{work}\n\n"
        f"Education:\n{education}"
        + (f"\n\nProjects:\n{projects}" if projects else "")
    )


def _render_job(job: Job) -> str:
    return (
        f"Title: {job.title}\n"
        f"Company: {job.company}\n"
        f"Location: {job.location or 'Not specified'}\n"
        f"Salary: {job.salary or 'Not specified'}\n"
        f"Description:\n{job.description or 'Not provided'}"
    )


def _load_master_resume(profile: UserProfile) -> str:
    if profile.md_path:
        p = Path(profile.md_path)
        if p.exists():
            return p.read_text(encoding="utf-8")
    return _render_profile(profile)


def _field_to_str(value: Any) -> str:
    """Render a profile/job field value to a human-readable string for prompt injection."""
    if isinstance(value, list):
        if not value:
            return ""
        first = value[0]
        if isinstance(first, WorkHistoryEntry):
            return "\n".join(
                f"- {e.title} at {e.company} ({e.start}–{e.end}): {e.summary}"
                for e in value  # type: ignore[union-attr]
            )
        if isinstance(first, EducationEntry):
            return "\n".join(
                f"- {e.degree} in {e.field} from {e.institution} ({e.graduated}), GPA {e.gpa}"
                for e in value  # type: ignore[union-attr]
            )
        if isinstance(first, ProjectEntry):
            return "\n".join(
                f"- {e.name}: {e.description}"
                + (f" ({e.url})" if e.url else "")
                + (f" — {', '.join(e.technologies)}" if e.technologies else "")
                for e in value  # type: ignore[union-attr]
            )
        return ", ".join(str(v) for v in value)
    if value is None:
        return ""
    return str(value)


def _apply_template(template: str, sources: dict[str, Any]) -> str:
    """Replace {table.field} placeholders using values from sources dict."""
    def _replace(m: re.Match) -> str:
        table, field = m.group(1), m.group(2)
        obj = sources.get(table)
        if obj is None:
            return m.group(0)
        value = getattr(obj, field, None)
        if value is None:
            return m.group(0)
        return _field_to_str(value)
    return re.sub(r'\{(\w+)\.(\w+)\}', _replace, template)


def build_prompt(job: Job, profile: UserProfile, template: str) -> str:
    # Pre-substitute the virtual {user_profile.master_resume} placeholder, which reads
    # from md_path if present rather than reconstructing from structured fields.
    master = _load_master_resume(profile)
    template = template.replace("{user_profile.master_resume}", master)
    return _apply_template(template, {"job": job, "user_profile": profile})


# Keep old names as aliases — existing tests and imports continue to work
build_resume_prompt = build_prompt
build_cover_prompt = build_prompt


def build_description_prompt(job: Job, template: str) -> str:
    result = _apply_template(template, {"job": job})
    # Also support bare {field} placeholders (e.g., {description}, {title})
    def _bare_replace(m: re.Match) -> str:
        value = getattr(job, m.group(1), None)
        return _field_to_str(value) if value is not None else m.group(0)
    return re.sub(r'\{(\w+)\}', _bare_replace, result)


def _run_extraction(job: Job, db: Session) -> str:
    """Return extraction JSON for job, running LLM if not already cached.

    If job.extraction_json is already populated, returns it immediately.
    Otherwise: resolves active description prompt, calls LLM, strips markdown
    code fences from the response, stores result in job.extraction_json, commits,
    and returns the JSON string.
    """
    if job.extraction_json:
        return job.extraction_json

    prompt_cfg = _resolve_active_prompt(db, "description")
    actual_prompt = build_description_prompt(job, prompt_cfg["content"])
    client, model = get_client_for_named_provider(db, prompt_cfg["provider_name"], prompt_cfg["model_id"])

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": actual_prompt}],
    )
    raw = response.choices[0].message.content or ""
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
    raw = re.sub(r"\s*```$", "", raw.strip())
    result = raw.strip()

    job.extraction_json = result
    db.commit()
    return result


def extraction_json_to_markdown(data: dict) -> str:
    """Converts structured extraction JSON to human-readable markdown."""
    sections = []

    meta = []
    for key, label in [
        ("seniority", "Seniority"),
        ("role_type", "Role Type"),
        ("domain", "Domain"),
        ("work_arrangement", "Work Arrangement"),
        ("employment_type", "Employment Type"),
    ]:
        if val := data.get(key):
            meta.append(f"**{label}:** {val}")
    if meta:
        sections.append("## Overview\n\n" + "\n\n".join(meta))

    for key, heading in [
        ("required_skills", "Required Skills"),
        ("preferred_skills", "Preferred Skills"),
        ("tech_stack", "Tech Stack"),
        ("key_responsibilities", "Key Responsibilities"),
        ("company_signals", "Company Signals"),
    ]:
        if items := data.get(key):
            sections.append(f"## {heading}\n" + "\n".join(f"- {item}" for item in items))

    return "\n\n".join(sections)


def _build_frontmatter(
    profile: UserProfile,
    github: str = "",
    linkedin: str = "",
    website: str = "",
) -> str:
    full_name = profile.name or f"{profile.first_name} {profile.last_name}".strip()
    firstname = profile.first_name or full_name.split(" ", 1)[0]
    lastname = profile.last_name or (full_name.split(" ", 1)[1] if " " in full_name else "")
    lines = [
        "---",
        f"name: {full_name}",
        f"firstname: {firstname}",
        f"lastname: {lastname}",
        f"email: {profile.email}",
        f"phone: {profile.phone}",
        f"location: {profile.location}",
    ]
    if github:
        lines.append(f"github: {github}")
    if linkedin:
        lines.append(f"linkedin: {linkedin}")
    if website:
        lines.append(f"website: {website}")
    lines.extend(["---", ""])
    return "\n".join(lines) + "\n"


def generate_md(
    job_key: str,
    type_: str,
    prompt_content: str,
    client: Any,
    model: str,
    db: Session,
) -> None:
    """Generate resume or cover letter markdown for a job. Raises on failure."""
    job = db.query(Job).filter_by(job_key=job_key).first()
    if job is None:
        raise RuntimeError(f"Job {job_key!r} not found")

    row = db.query(UserProfileModel).first()
    if not row:
        raise RuntimeError("No user profile found in DB.")
    data = json.loads(row.data)
    import dataclasses as _dc
    data["work_history"] = [WorkHistoryEntry(**e) for e in data.get("work_history", [])]
    data["education"] = [EducationEntry(**e) for e in data.get("education", [])]
    data["projects"] = [ProjectEntry(**e) for e in data.get("projects", [])]
    _profile_fields = {f.name for f in _dc.fields(UserProfile)}
    profile = UserProfile(**{k: v for k, v in data.items() if k in _profile_fields})

    frontmatter = _build_frontmatter(
        profile,
        github=_db_cfg(db, "resume_github"),
        linkedin=_db_cfg(db, "resume_linkedin"),
        website=_db_cfg(db, "resume_website"),
    )

    _OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    md_path = _OUTPUTS_DIR / f"{job_key}_{type_}.md"
    content = call_claude(build_prompt(job, profile, prompt_content), client, model)
    if type_ == "resume":
        content = strip_header_block(content)
    md_path.write_text(frontmatter + content, encoding="utf-8")


def generate_pdf(
    job_key: str,
    type_: str,
    template_path: Path,
    db: Session,
) -> None:
    """Render PDF from existing markdown for a job and update job DB record. Raises on failure."""
    md_path = _OUTPUTS_DIR / f"{job_key}_{type_}.md"
    if not md_path.exists():
        raise FileNotFoundError(f"Markdown not found: {md_path}")

    _OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    pdf_path = _OUTPUTS_DIR / f"{job_key}_{type_}.pdf"

    if type_ == "resume":
        render_resume_pdf(md_path, pdf_path, job_key, template_path)
    else:
        render_pdf(md_path, pdf_path, template_path)

    job = db.query(Job).filter_by(job_key=job_key).first()
    if job is None:
        raise RuntimeError(f"Job {job_key!r} not found after PDF render")
    if type_ == "resume":
        job.resume_path = str(pdf_path)
    else:
        job.cover_path = str(pdf_path)
    db.commit()


def strip_header_block(md: str) -> str:
    """Remove name/contact header if LLM included one despite instructions."""
    lines = md.splitlines()
    i = 0
    if lines and lines[0].strip() == "---":
        i = 1
        while i < len(lines):
            if lines[i].strip() == "---":
                i += 1
                break
            i += 1
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("## "):
            break
        if i >= 10:
            break
        i += 1
    return "\n".join(lines[i:])


def call_claude(prompt: str, client: Any, model: str) -> str:
    response = client.chat.completions.create(
        model=model,
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )
    choice = response.choices[0]
    content = choice.message.content
    if not content:
        raise RuntimeError(f"LLM returned empty response (finish_reason={choice.finish_reason!r})")
    return content.strip()


def render_pdf(md_path: Path, pdf_path: Path, template_path: Path) -> None:
    subprocess.run(
        [
            "pandoc", str(md_path),
            "-o", str(pdf_path),
            "--pdf-engine=xelatex",
            f"--template={template_path}",
        ],
        check=True,
    )


def _get_page_count(pdf_path: Path) -> int:
    result = subprocess.run(
        ["pdfinfo", str(pdf_path)], capture_output=True, text=True, check=True
    )
    for line in result.stdout.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":")[1].strip())
    raise RuntimeError(f"Could not determine page count for {pdf_path.name}")


def render_resume_pdf(md_path: Path, pdf_path: Path, job_key: str, template_path: Optional[Path] = None) -> None:
    """Render resume PDF, reducing font/margins to fit one page if needed."""
    tpl = template_path or _DEFAULT_RESUME_TEMPLATE
    attempts = [
        {"fontsize": "11pt", "top": "1.0in", "bottom": "1.0in"},
        {"fontsize": "10pt", "top": "1.0in", "bottom": "1.0in"},
        {"fontsize": "10pt", "top": "0.8in", "bottom": "0.8in"},
    ]
    template_text = tpl.read_text(encoding="utf-8")
    for s in attempts:
        modified = re.sub(
            r"\\documentclass\[\d+pt\]",
            f"\\\\documentclass[{s['fontsize']}]",
            template_text,
        )
        modified = re.sub(
            r"top=[\d.]+in, bottom=[\d.]+in",
            f"top={s['top']}, bottom={s['bottom']}",
            modified,
        )
        with tempfile.NamedTemporaryFile(
            suffix=".tex", delete=False, mode="w", encoding="utf-8"
        ) as f:
            f.write(modified)
            tmp = Path(f.name)
        try:
            render_pdf(md_path, pdf_path, tmp)
            if _get_page_count(pdf_path) <= 1:
                return
        finally:
            tmp.unlink(missing_ok=True)
    raise RuntimeError(
        f"Resume '{job_key}' exceeds 1 page at minimum settings (10pt, 0.8in margins)."
    )


def _db_cfg(db: Session, key: str) -> str:
    """Read a config value from the DB; returns empty string if absent."""
    row = db.query(Config).filter_by(key=key).first()
    return row.value if row else ""


def _resolve_active_prompt(db: Session, type_: str) -> dict:
    """Return the active prompt config dict for a type. Raises RuntimeError if not configured."""
    active_id = _db_cfg(db, f"active_{type_}_prompt_id")
    prompts = json.loads(_db_cfg(db, f"{type_}_prompts") or "[]")
    prompt = next((p for p in prompts if p["id"] == active_id), None)
    if not prompt:
        raise RuntimeError(f"No active {type_} prompt configured. Set one under Config → Scaffolding.")
    return prompt


def _resolve_latex_template(db: Session, template_name: str) -> Path:
    """Return the filesystem Path for a named LaTeX template. Raises RuntimeError if not found."""
    if not template_name:
        raise RuntimeError("No LaTeX template configured for this prompt.")
    templates = json.loads(_db_cfg(db, "latex_templates") or "[]")
    match = next((t for t in templates if t["name"] == template_name), None)
    if not match:
        raise RuntimeError(f"LaTeX template '{template_name}' not found in config.")
    p = Path(match["path"])
    if not p.exists():
        raise RuntimeError(f"LaTeX template file missing: {p}")
    return p


def generate_resume(job_key: str, db: Session) -> None:
    """Resolve active resume prompt config and generate MD + PDF."""
    prompt = _resolve_active_prompt(db, "resume")
    client, model = get_client_for_named_provider(db, prompt["provider_name"], prompt["model_id"])
    generate_md(job_key, "resume", prompt["content"], client, model, db)
    template_path = _resolve_latex_template(db, prompt.get("template_name", ""))
    generate_pdf(job_key, "resume", template_path, db)


def generate_cover(job_key: str, db: Session) -> None:
    """Resolve active cover prompt config and generate MD + PDF."""
    prompt = _resolve_active_prompt(db, "cover")
    client, model = get_client_for_named_provider(db, prompt["provider_name"], prompt["model_id"])
    generate_md(job_key, "cover", prompt["content"], client, model, db)
    template_path = _resolve_latex_template(db, prompt.get("template_name", ""))
    generate_pdf(job_key, "cover", template_path, db)


def generate_job(job_key: str, db: Optional[Session] = None) -> None:
    """Generate resume and cover letter for a job. Errors are printed to stderr."""
    own_db = db is None
    if own_db:
        db = SessionLocal()
    try:
        generate_resume(job_key, db)
        generate_cover(job_key, db)
    except Exception as e:
        # Swallow so the all-at-once endpoint can return a partial result
        print(f"[generator] ERROR for {job_key}: {e}", file=sys.stderr)
    finally:
        if own_db:
            db.close()
