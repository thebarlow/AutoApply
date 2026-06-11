from __future__ import annotations

import json
import textwrap
from pathlib import Path

from sqlalchemy.orm import Session

from db.database import Config, FieldHelp

_PROMPTS_DEFAULTS_DIR = Path(__file__).parent.parent / "prompts" / "defaults"

PROMPT_TYPE_KEYS = (
    "scoring", "resume", "cover", "extraction", "resume_parse",
    "resume_eval", "resume_refine", "cover_eval", "cover_refine",
)

DEFAULT_CONFIG: dict[str, str] = {
    "w1": "0.5",
    "w2": "0.5",
    "auto_reject_threshold": "0.3",
    "auto_approve_threshold": "0.8",
    "keywords_whitelist": "[]",
    "keywords_blacklist": "[]",
    "location": "",
    "remote_only": "true",
    "full_time_only": "true",
    "target_salary_min": "0",
    "benefits_priorities": "[]",
    "resume_github": "",
    "resume_linkedin": "",
    "resume_website": "",
    "resume_prompt_template": textwrap.dedent("""\
    You are writing a tailored one-page resume in Markdown for a job application.

    # Candidate Profile
    {profile}

    # Job Posting
    {job}

    # Instructions
    - Output ONLY the resume Markdown body. No preamble, no explanation.
    - Do NOT include a name or contact block — those are handled separately.
    - Start directly with the first section header (e.g. ## Profile).
    - Do not use `---` horizontal rules between sections.
    - Do not invent experience or skills not in the candidate profile.
    - Drop the Soft Skills section entirely.

    ## Profile
    - Max 500 characters total.

    ## Education
    - Always include all degrees exactly as written. No bullets.

    ## Experience
    - Always include all entries.
    - Max 2 bullets per entry, each bullet max 120 characters.
    - Stress skills and responsibilities directly mentioned in the job description.

    ## Projects
    - Reorder by relevance to this job. Drop least relevant project(s) if needed.
    - Always include at least 2, max 4 projects.
    - 1 bullet per project, max 120 characters.

    ## Skills
    - Always include Python, Git, Docker, SQL regardless of job description.
    - Include only categories that have 2 or more relevant skills for this job.
    - If a category has only 1 relevant skill, fold it into the nearest adjacent category.
    - Sort categories by relevance to the job description.
    - Within each category, list skills directly mentioned in the job description first.
    - Max 6 categories.
    """),
    "cover_prompt_template": textwrap.dedent("""\
    You are writing a concise cover letter in Markdown for a job application.

    # Candidate Profile
    {profile}

    # Job Posting
    {job}

    # Instructions
    - Output ONLY the cover letter Markdown. No preamble, no explanation.
    - Do not use `---` horizontal rules anywhere in the output.
    - Exactly 3 paragraphs: (1) fit and interest, (2) specific value-add tied to the job description, (3) close.
    - Address it to the hiring team at the company listed in the job posting.
    - Do not include a sign-off, name, or contact information at the end — those are added automatically.
    - Do not invent experience or skills not in the candidate profile.
    """),
    "max_jobs_per_source": "50",
    "scraper_sources": "remotive,remoteok",
}


JOB_FIELD_DESCRIPTIONS: dict[str, str] = {
    "id": "Internal auto-increment primary key.",
    "job_key": "Unique identifier for the posting (source + external ID).",
    "source": "Scraper that collected the job (e.g. remotive, remoteok, linkedin).",
    "title": "Job title as listed in the posting.",
    "company": "Company name.",
    "location": "Office location or 'Remote'.",
    "salary": "Salary or compensation range as listed.",
    "remote": "True if the position is explicitly remote.",
    "description": "Full job description text.",
    "url": "Link to the original job posting.",
    "posted_at": "When the job was originally posted (ISO string).",
    "scraped_at": "When this job was collected by the scraper (ISO string).",
    "state": "Current pipeline state (draft, pending, applied, rejected, etc.).",
    "desirability_score": "How desirable the role is based on your profile (0–10).",
    "fit_score": "How well you fit the job requirements (0–10).",
    "final_score": "Weighted composite of desirability and fit scores (0–10).",
    "score_justification": "Claude's reasoning for the scores.",
    "resume_path": "Filesystem path to the generated resume PDF for this job.",
    "cover_path": "Filesystem path to the generated cover letter PDF.",
    "extraction_json": "Structured data extracted from the job description (JSON string).",
    "applied_at": "When the application was submitted (ISO string).",
    "sheets_row_id": "Google Sheets row ID for external application tracking.",
}


USER_PROFILE_FIELD_DESCRIPTIONS: dict[str, str] = {
    "name": "Your full name as it appears on your resume.",
    "email": "Your contact email address.",
    "phone": "Your phone number.",
    "location": "Your city or region (e.g. 'New York, NY' or 'Remote').",
    "skills": "Flat list of your technical and professional skills.",
    "work_history": "List of past roles with company, title, dates, and a summary of responsibilities.",
    "education": "Degrees earned: institution, degree type, field of study, graduation year, and GPA.",
    "projects": "Personal, academic, or side projects with name, description, URL, and technologies used.",
    "target_salary_min": "Minimum acceptable annual salary (integer, USD).",
    "target_salary_max": "Maximum target annual salary (integer, USD).",
    "target_roles": "Job titles or role types you are actively targeting.",
}


def seed_field_help(db: Session) -> None:
    """Insert default field descriptions for the jobs table if not already present."""
    for column_name, description in JOB_FIELD_DESCRIPTIONS.items():
        existing = db.query(FieldHelp).filter_by(table_name="jobs", column_name=column_name).first()
        if not existing:
            db.add(FieldHelp(table_name="jobs", column_name=column_name, description=description))
    db.commit()


def seed_user_profile_field_help(db: Session) -> None:
    """Insert default field descriptions for user_profile fields if not already present."""
    for column_name, description in USER_PROFILE_FIELD_DESCRIPTIONS.items():
        existing = db.query(FieldHelp).filter_by(table_name="user_profile", column_name=column_name).first()
        if not existing:
            db.add(FieldHelp(table_name="user_profile", column_name=column_name, description=description))
    db.commit()


def seed_default_config(db: Session) -> None:
    """Insert default config entries if they do not already exist."""
    for key, value in DEFAULT_CONFIG.items():
        if not db.query(Config).filter_by(key=key).first():
            db.add(Config(key=key, value=value))
    db.commit()


def seed_prompt_defaults(db: Session) -> None:
    """Seed prompt_defaults from prompts/defaults/*.md, only for missing rows.

    The shipped .md files are one-time seed data; existing rows (which may have
    been edited in the DB) are never overwritten.
    """
    from db.database import PromptDefault

    for type_key in PROMPT_TYPE_KEYS:
        if db.query(PromptDefault).filter_by(type_key=type_key).first():
            continue
        path = _PROMPTS_DEFAULTS_DIR / f"{type_key}.md"
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        if not content.strip():
            continue
        db.add(PromptDefault(type_key=type_key, content=content))
    db.commit()


def migrate_file_prompts_to_db(db: Session) -> None:
    """Port file-path-based profile prompts into the prompts table.

    Idempotent: a profile that already has any prompts row is skipped. For each
    of the nine prompt types, reads content from the file path stored in the
    profile JSON (if it exists and exceeds 10 words), otherwise falls back to the
    prompt_defaults content. Model comes from the profile JSON. Does not modify
    the profile JSON.
    """
    from datetime import datetime, timezone
    from pathlib import Path
    from core.user import User
    from db.database import Prompt, PromptDefault

    defaults = {d.type_key: d.content for d in db.query(PromptDefault).all()}
    now = datetime.now(timezone.utc).isoformat()

    for profile in db.query(User).all():
        if db.query(Prompt).filter_by(profile_id=profile.id).first():
            continue
        data = json.loads(profile.data or "{}")
        for type_key in PROMPT_TYPE_KEYS:
            content = ""
            path_str = data.get(f"prompt_{type_key}", "")
            if path_str:
                p = Path(path_str)
                if p.exists():
                    text = p.read_text(encoding="utf-8")
                    if len(text.split()) > 10:
                        content = text
            if not content:
                content = defaults.get(type_key, "")
            model = data.get(f"prompt_{type_key}_model", "") or ""
            db.add(Prompt(
                profile_id=profile.id, type_key=type_key,
                content=content, model=model, updated_at=now,
            ))
    db.commit()


def seed_skill_aliases(db: Session, profile_id: int = 1) -> None:
    """Insert curated skill aliases for ``profile_id`` that aren't already present (idempotent)."""
    from db.database import SkillAlias
    from core.skill_analytics import seed_alias_pairs

    existing = {
        row.alias_key
        for row in db.query(SkillAlias).filter_by(profile_id=profile_id).all()
    }
    added = False
    for alias_key, canonical in seed_alias_pairs():
        if alias_key not in existing:
            db.add(SkillAlias(profile_id=profile_id, alias_key=alias_key, canonical=canonical))
            added = True
    if added:
        db.commit()
