from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from core.llm import get_openai_client
from core.types import JobState, UserProfile, WorkHistoryEntry, EducationEntry
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
    return (
        f"Name: {profile.name}\n"
        f"Target roles: {', '.join(profile.target_roles)}\n"
        f"Target salary: ${profile.target_salary_min}–${profile.target_salary_max}\n"
        f"Skills: {', '.join(profile.skills)}\n\n"
        f"Work History:\n{work}\n\n"
        f"Education:\n{education}"
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


def build_resume_prompt(job: Job, profile: UserProfile, template: str) -> str:
    return template.format(
        profile=_load_master_resume(profile),
        job=_render_job(job),
        master_resume=_load_master_resume(profile),
        title=job.title or "",
        company=job.company or "",
        location=job.location or "Not specified",
        description=job.description or "Not provided",
    )


def build_cover_prompt(job: Job, profile: UserProfile, template: str) -> str:
    return template.format(
        profile=_load_master_resume(profile),
        job=_render_job(job),
        master_resume=_load_master_resume(profile),
        title=job.title or "",
        company=job.company or "",
        location=job.location or "Not specified",
        description=job.description or "Not provided",
    )


def build_description_prompt(job: Job, template: str) -> str:
    """Renders the description extraction prompt template with job fields."""
    return template.format(
        title=job.title or "",
        company=job.company or "",
        location=job.location or "Not specified",
        description=job.description or "Not provided",
    )


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
    parts = profile.name.split(" ", 1)
    firstname = parts[0]
    lastname = parts[1] if len(parts) > 1 else ""
    lines = [
        "---",
        f"name: {profile.name}",
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


def generate_resume_md(
    job_key: str,
    db: Optional[Session] = None,
    client: Optional[Any] = None,
    model: Optional[str] = None,
) -> None:
    """Generate resume markdown for a job."""
    own_db = db is None
    if own_db:
        db = SessionLocal()

    try:
        if client is None or model is None:
            client, model = get_openai_client(db)

        job = db.query(Job).filter_by(job_key=job_key).first()
        if job is None:
            return

        row = db.query(UserProfileModel).first()
        if not row:
            raise RuntimeError("No user profile found in DB.")
        data = json.loads(row.data)
        data["work_history"] = [WorkHistoryEntry(**e) for e in data.get("work_history", [])]
        data["education"] = [EducationEntry(**e) for e in data.get("education", [])]
        profile = UserProfile(**data)

        resume_tpl = db.query(Config).filter_by(key="resume_prompt_template").first()
        if not resume_tpl:
            raise RuntimeError("Prompt templates not seeded in config table.")

        def _cfg(key: str) -> str:
            r = db.query(Config).filter_by(key=key).first()
            return r.value if r else ""

        frontmatter = _build_frontmatter(
            profile,
            github=_cfg("resume_github"),
            linkedin=_cfg("resume_linkedin"),
            website=_cfg("resume_website"),
        )

        _OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        resume_md_path = _OUTPUTS_DIR / f"{job_key}_resume.md"
        resume_md = strip_header_block(
            call_claude(build_resume_prompt(job, profile, resume_tpl.value), client, model)
        )
        resume_md_path.write_text(frontmatter + resume_md, encoding="utf-8")

    except Exception as e:
        print(f"[generator] ERROR for {job_key}: {e}", file=sys.stderr)
    finally:
        if own_db:
            db.close()


def generate_resume_pdf(
    job_key: str,
    db: Optional[Session] = None,
) -> None:
    """Render resume PDF from existing markdown for a job and set state to GENERATED."""
    own_db = db is None
    if own_db:
        db = SessionLocal()

    job = None
    try:
        resume_md_path = _OUTPUTS_DIR / f"{job_key}_resume.md"
        if not resume_md_path.exists():
            raise FileNotFoundError(f"Resume markdown not found: {resume_md_path}")

        def _cfg(key: str) -> str:
            r = db.query(Config).filter_by(key=key).first()
            return r.value if r else ""

        resume_tpl_path = Path(_cfg("resume_template_path")) if _cfg("resume_template_path") else None

        _OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        resume_pdf_path = _OUTPUTS_DIR / f"{job_key}_resume.pdf"
        render_resume_pdf(resume_md_path, resume_pdf_path, job_key, resume_tpl_path)

        job = db.query(Job).filter_by(job_key=job_key).first()
        if job:
            job.resume_path = str(resume_pdf_path)
            db.commit()

    except Exception as e:
        print(f"[generator] ERROR for {job_key}: {e}", file=sys.stderr)
    finally:
        if own_db:
            db.close()


def generate_resume(
    job_key: str,
    db: Optional[Session] = None,
    client: Optional[Any] = None,
    model: Optional[str] = None,
) -> None:
    """Generate resume markdown and PDF for a job."""
    generate_resume_md(job_key, db=db, client=client, model=model)
    generate_resume_pdf(job_key, db=db)


def generate_cover_md(
    job_key: str,
    db: Optional[Session] = None,
    client: Optional[Any] = None,
    model: Optional[str] = None,
) -> None:
    """Generate cover letter markdown for a job."""
    own_db = db is None
    if own_db:
        db = SessionLocal()

    try:
        if client is None or model is None:
            client, model = get_openai_client(db)

        job = db.query(Job).filter_by(job_key=job_key).first()
        if job is None:
            return

        row = db.query(UserProfileModel).first()
        if not row:
            raise RuntimeError("No user profile found in DB.")
        data = json.loads(row.data)
        data["work_history"] = [WorkHistoryEntry(**e) for e in data.get("work_history", [])]
        data["education"] = [EducationEntry(**e) for e in data.get("education", [])]
        profile = UserProfile(**data)

        cover_tpl = db.query(Config).filter_by(key="cover_prompt_template").first()
        if not cover_tpl:
            raise RuntimeError("Prompt templates not seeded in config table.")

        def _cfg(key: str) -> str:
            r = db.query(Config).filter_by(key=key).first()
            return r.value if r else ""

        frontmatter = _build_frontmatter(
            profile,
            github=_cfg("resume_github"),
            linkedin=_cfg("resume_linkedin"),
            website=_cfg("resume_website"),
        )

        _OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        cover_md_path = _OUTPUTS_DIR / f"{job_key}_cover.md"
        cover_md = call_claude(build_cover_prompt(job, profile, cover_tpl.value), client, model)
        cover_md_path.write_text(frontmatter + cover_md, encoding="utf-8")

    except Exception as e:
        print(f"[generator] ERROR for {job_key}: {e}", file=sys.stderr)
    finally:
        if own_db:
            db.close()


def generate_cover_pdf(
    job_key: str,
    db: Optional[Session] = None,
) -> None:
    """Render cover letter PDF from existing markdown for a job."""
    own_db = db is None
    if own_db:
        db = SessionLocal()

    try:
        cover_md_path = _OUTPUTS_DIR / f"{job_key}_cover.md"
        if not cover_md_path.exists():
            raise FileNotFoundError(f"Cover markdown not found: {cover_md_path}")

        def _cfg(key: str) -> str:
            r = db.query(Config).filter_by(key=key).first()
            return r.value if r else ""

        cover_tpl_path = Path(_cfg("cover_template_path")) if _cfg("cover_template_path") else _DEFAULT_COVER_TEMPLATE

        _OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        cover_pdf_path = _OUTPUTS_DIR / f"{job_key}_cover.pdf"
        render_pdf(cover_md_path, cover_pdf_path, cover_tpl_path)

        job = db.query(Job).filter_by(job_key=job_key).first()
        if job:
            job.cover_path = str(cover_pdf_path)
            db.commit()

    except Exception as e:
        print(f"[generator] ERROR for {job_key}: {e}", file=sys.stderr)
    finally:
        if own_db:
            db.close()


def generate_cover(
    job_key: str,
    db: Optional[Session] = None,
    client: Optional[Any] = None,
    model: Optional[str] = None,
) -> None:
    """Generate cover letter markdown and PDF for a job."""
    generate_cover_md(job_key, db=db, client=client, model=model)
    generate_cover_pdf(job_key, db=db)


def generate_job(
    job_key: str,
    db: Optional[Session] = None,
    client: Optional[Any] = None,
    model: Optional[str] = None,
) -> None:
    """Generate resume and cover letter for an approved job."""
    generate_resume(job_key, db=db, client=client, model=model)
    generate_cover(job_key, db=db, client=client, model=model)
