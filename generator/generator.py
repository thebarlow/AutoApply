from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional

import anthropic
from dotenv import load_dotenv
from sqlalchemy.orm import Session

from core.types import JobState, UserProfile, WorkHistoryEntry, EducationEntry
from db.database import SessionLocal
from db.models import Config, Job, UserProfileModel

load_dotenv()

_GENERATOR_DIR = Path(__file__).parent
_OUTPUTS_DIR = _GENERATOR_DIR / "outputs"
RESUME_TEMPLATE_PATH = _GENERATOR_DIR / "resume_template.tex"
COVER_TEMPLATE_PATH = _GENERATOR_DIR / "cover_template.tex"


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


def build_resume_prompt(job: Job, profile: UserProfile, template: str) -> str:
    return template.format(profile=_render_profile(profile), job=_render_job(job))


def build_cover_prompt(job: Job, profile: UserProfile, template: str) -> str:
    return template.format(profile=_render_profile(profile), job=_render_job(job))


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
    """Remove name/contact header if Claude included one despite instructions."""
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
        if i >= 10:  # bail if no section heading found in preamble
            break
        i += 1
    return "\n".join(lines[i:])


def call_claude(prompt: str, client: Any) -> str:
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()


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


def render_resume_pdf(md_path: Path, pdf_path: Path, job_key: str) -> None:
    """Render resume PDF, reducing font/margins to fit one page if needed."""
    attempts = [
        {"fontsize": "11pt", "top": "1.0in", "bottom": "1.0in"},
        {"fontsize": "10pt", "top": "1.0in", "bottom": "1.0in"},
        {"fontsize": "10pt", "top": "0.8in", "bottom": "0.8in"},
    ]
    template_text = RESUME_TEMPLATE_PATH.read_text(encoding="utf-8")
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


def generate_job(
    job_key: str,
    db: Optional[Session] = None,
    client: Optional[anthropic.Anthropic] = None,
) -> None:
    """Generate resume and cover letter for an approved job. Thread entry point."""
    own_db = db is None
    if own_db:
        db = SessionLocal()
    if client is None:
        client = anthropic.Anthropic()

    job = None
    try:
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
        cover_tpl = db.query(Config).filter_by(key="cover_prompt_template").first()
        if not resume_tpl or not cover_tpl:
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

        outputs = _OUTPUTS_DIR
        outputs.mkdir(parents=True, exist_ok=True)

        resume_md_path = outputs / f"{job_key}_resume.md"
        resume_pdf_path = outputs / f"{job_key}_resume.pdf"
        resume_md = strip_header_block(
            call_claude(build_resume_prompt(job, profile, resume_tpl.value), client)
        )
        resume_md_path.write_text(frontmatter + resume_md, encoding="utf-8")
        render_resume_pdf(resume_md_path, resume_pdf_path, job_key)

        cover_md_path = outputs / f"{job_key}_cover.md"
        cover_pdf_path = outputs / f"{job_key}_cover.pdf"
        cover_md = call_claude(build_cover_prompt(job, profile, cover_tpl.value), client)
        cover_md_path.write_text(frontmatter + cover_md, encoding="utf-8")
        render_pdf(cover_md_path, cover_pdf_path, COVER_TEMPLATE_PATH)

        job.resume_path = str(resume_pdf_path)
        job.cover_path = str(cover_pdf_path)
        db.commit()

    except Exception as e:
        print(f"[generator] ERROR for {job_key}: {e}", file=sys.stderr)
        try:
            job = db.query(Job).filter_by(job_key=job_key).first()
            if job:
                job.state = JobState.FAILED.value
                db.commit()
        except Exception:
            pass
    finally:
        if own_db:
            db.close()


def generate_resume_for_job(
    job_key: str,
    db: Optional[Session] = None,
    client: Optional[anthropic.Anthropic] = None,
) -> None:
    """Generate resume only for a job. Updates job.resume_path and commits."""
    own_db = db is None
    if own_db:
        db = SessionLocal()
    if client is None:
        client = anthropic.Anthropic()

    try:
        job = db.query(Job).filter_by(job_key=job_key).first()
        if job is None:
            raise ValueError(f"Job not found: {job_key}")

        row = db.query(UserProfileModel).first()
        if not row:
            raise RuntimeError("No user profile found in DB.")
        data = json.loads(row.data)
        data["work_history"] = [WorkHistoryEntry(**e) for e in data.get("work_history", [])]
        data["education"] = [EducationEntry(**e) for e in data.get("education", [])]
        profile = UserProfile(**data)

        resume_tpl = db.query(Config).filter_by(key="resume_prompt_template").first()
        if not resume_tpl:
            raise RuntimeError("resume_prompt_template not seeded in config table.")

        def _cfg(key: str) -> str:
            r = db.query(Config).filter_by(key=key).first()
            return r.value if r else ""

        frontmatter = _build_frontmatter(
            profile,
            github=_cfg("resume_github"),
            linkedin=_cfg("resume_linkedin"),
            website=_cfg("resume_website"),
        )

        outputs = _OUTPUTS_DIR
        outputs.mkdir(parents=True, exist_ok=True)

        resume_md_path = outputs / f"{job_key}_resume.md"
        resume_pdf_path = outputs / f"{job_key}_resume.pdf"
        resume_md = strip_header_block(
            call_claude(build_resume_prompt(job, profile, resume_tpl.value), client)
        )
        resume_md_path.write_text(frontmatter + resume_md, encoding="utf-8")
        render_resume_pdf(resume_md_path, resume_pdf_path, job_key)

        job.resume_path = str(resume_pdf_path)
        db.commit()

    except Exception as e:
        print(f"[generator] ERROR generating resume for {job_key}: {e}", file=sys.stderr)
        raise
    finally:
        if own_db:
            db.close()


def generate_cover_for_job(
    job_key: str,
    db: Optional[Session] = None,
    client: Optional[anthropic.Anthropic] = None,
) -> None:
    """Generate cover letter only for a job. Updates job.cover_path and commits."""
    own_db = db is None
    if own_db:
        db = SessionLocal()
    if client is None:
        client = anthropic.Anthropic()

    try:
        job = db.query(Job).filter_by(job_key=job_key).first()
        if job is None:
            raise ValueError(f"Job not found: {job_key}")

        row = db.query(UserProfileModel).first()
        if not row:
            raise RuntimeError("No user profile found in DB.")
        data = json.loads(row.data)
        data["work_history"] = [WorkHistoryEntry(**e) for e in data.get("work_history", [])]
        data["education"] = [EducationEntry(**e) for e in data.get("education", [])]
        profile = UserProfile(**data)

        cover_tpl = db.query(Config).filter_by(key="cover_prompt_template").first()
        if not cover_tpl:
            raise RuntimeError("cover_prompt_template not seeded in config table.")

        def _cfg(key: str) -> str:
            r = db.query(Config).filter_by(key=key).first()
            return r.value if r else ""

        frontmatter = _build_frontmatter(
            profile,
            github=_cfg("resume_github"),
            linkedin=_cfg("resume_linkedin"),
            website=_cfg("resume_website"),
        )

        outputs = _OUTPUTS_DIR
        outputs.mkdir(parents=True, exist_ok=True)

        cover_md_path = outputs / f"{job_key}_cover.md"
        cover_pdf_path = outputs / f"{job_key}_cover.pdf"
        cover_md = call_claude(build_cover_prompt(job, profile, cover_tpl.value), client)
        cover_md_path.write_text(frontmatter + cover_md, encoding="utf-8")
        render_pdf(cover_md_path, cover_pdf_path, COVER_TEMPLATE_PATH)

        job.cover_path = str(cover_pdf_path)
        db.commit()

    except Exception as e:
        print(f"[generator] ERROR generating cover for {job_key}: {e}", file=sys.stderr)
        raise
    finally:
        if own_db:
            db.close()
