from __future__ import annotations

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
    "resume_prompt_template": (
        "You are writing a tailored one-page resume in Markdown for a job application.\n\n"
        "# Candidate Profile\n{profile}\n\n"
        "# Job Posting\n{job}\n\n"
        "# Instructions\n"
        "- Output ONLY the resume Markdown body. No preamble, no explanation.\n"
        "- Do NOT include a name or contact block — those are handled separately.\n"
        "- Start directly with the first section header (e.g. ## Profile).\n"
        "- Do not use `---` horizontal rules between sections.\n"
        "- Do not invent experience or skills not in the candidate profile.\n"
        "- Drop the Soft Skills section entirely.\n\n"
        "## Profile\n"
        "- Max 500 characters total.\n\n"
        "## Education\n"
        "- Always include all degrees exactly as written. No bullets.\n\n"
        "## Experience\n"
        "- Always include all entries.\n"
        "- Max 2 bullets per entry, each bullet max 120 characters.\n"
        "- Stress skills and responsibilities directly mentioned in the job description.\n\n"
        "## Projects\n"
        "- Reorder by relevance to this job. Drop least relevant project(s) if needed.\n"
        "- Always include at least 2, max 4 projects.\n"
        "- 1 bullet per project, max 120 characters.\n\n"
        "## Skills\n"
        "- Always include Python, Git, Docker, SQL regardless of job description.\n"
        "- Include only categories that have 2 or more relevant skills for this job.\n"
        "- If a category has only 1 relevant skill, fold it into the nearest adjacent category.\n"
        "- Sort categories by relevance to the job description.\n"
        "- Within each category, list skills directly mentioned in the job description first.\n"
        "- Max 6 categories."
    ),
    "cover_prompt_template": (
        "You are writing a concise cover letter in Markdown for a job application.\n\n"
        "# Candidate Profile\n{profile}\n\n"
        "# Job Posting\n{job}\n\n"
        "# Instructions\n"
        "- Output ONLY the cover letter Markdown. No preamble, no explanation.\n"
        "- Do not use `---` horizontal rules anywhere in the output.\n"
        "- Exactly 3 paragraphs: (1) fit and interest, (2) specific value-add tied to the job description, (3) close.\n"
        "- Address it to the hiring team at the company listed in the job posting.\n"
        "- Do not include a sign-off, name, or contact information at the end — those are added automatically.\n"
        "- Do not invent experience or skills not in the candidate profile."
    ),
}


def seed_default_config(db: Session) -> None:
    """Insert default config entries if they do not already exist."""
    for key, value in DEFAULT_CONFIG.items():
        if not db.query(Config).filter_by(key=key).first():
            db.add(Config(key=key, value=value))
    db.commit()
