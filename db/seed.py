from __future__ import annotations

import json
import textwrap
from pathlib import Path

from sqlalchemy.orm import Session

from db.database import Config, FieldHelp

_GENERATOR_DIR = Path(__file__).parent.parent / "generator"

DEFAULT_LATEX_TEMPLATES = [
    {
        "id": "default-resume",
        "name": "Default Resume",
        "path": str((_GENERATOR_DIR / "resume_template.tex").resolve()),
    },
    {
        "id": "default-cover",
        "name": "Default Cover Letter",
        "path": str((_GENERATOR_DIR / "cover_template.tex").resolve()),
    },
]

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


def seed_latex_templates(db: Session) -> None:
    """Register default LaTeX templates if not already present."""
    row = db.query(Config).filter_by(key="latex_templates").first()
    existing: list[dict] = json.loads(row.value) if row else []
    existing_ids = {t["id"] for t in existing}
    added = False
    for tpl in DEFAULT_LATEX_TEMPLATES:
        if tpl["id"] not in existing_ids and Path(tpl["path"]).exists():
            existing.append(tpl)
            added = True
    if added:
        if row:
            row.value = json.dumps(existing)
        else:
            db.add(Config(key="latex_templates", value=json.dumps(existing)))
        db.commit()
