from __future__ import annotations

import textwrap

from sqlalchemy.orm import Session

from db.models import Config

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
}


def seed_default_config(db: Session) -> None:
    """Insert default config entries if they do not already exist."""
    for key, value in DEFAULT_CONFIG.items():
        if not db.query(Config).filter_by(key=key).first():
            db.add(Config(key=key, value=value))
    db.commit()
