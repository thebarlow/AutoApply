"""Job scorer: scores SCRAPED jobs using Claude and transitions their state."""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from typing import Optional

import anthropic
from sqlalchemy.orm import Session

from core.types import JobState, UserProfile, WorkHistoryEntry, EducationEntry
from db.database import SessionLocal
from db.models import Config, Job, UserProfileModel


def compute_final_score(w1: float, w2: float, desirability: float, fit: float) -> float:
    """Compute weighted final score, clamped to [0.0, 1.0]."""
    return max(0.0, min(1.0, w1 * desirability + w2 * fit))


def determine_state(
    final: float, reject_threshold: float, approve_threshold: float
) -> JobState:
    """Map a final score to a JobState based on thresholds."""
    if final < reject_threshold:
        return JobState.REJECTED
    if final >= approve_threshold:
        return JobState.APPROVED
    return JobState.PENDING_REVIEW


def load_user_profile(db: Session) -> UserProfile:
    """Load UserProfile from DB. Exits if none found."""
    row = db.query(UserProfileModel).first()
    if not row:
        print("No user profile found. Run scripts/seed_profile.py first.", file=sys.stderr)
        sys.exit(1)

    data = json.loads(row.data)
    data["work_history"] = [WorkHistoryEntry(**e) for e in data.get("work_history", [])]
    data["education"] = [EducationEntry(**e) for e in data.get("education", [])]
    return UserProfile(**data)


def load_config(db: Session) -> dict[str, float]:
    """Load scoring weights and thresholds from the config table."""
    keys = ["w1", "w2", "auto_reject_threshold", "auto_approve_threshold"]
    result = {}
    for key in keys:
        row = db.query(Config).filter_by(key=key).first()
        result[key] = float(row.value) if row else 0.5
    return result


def build_prompt(job: Job, profile: UserProfile) -> str:
    """Build the Claude scoring prompt for a single job."""
    work_history_text = "\n".join(
        f"- {e.title} at {e.company} ({e.start}–{e.end}): {e.summary}"
        for e in profile.work_history
    )
    education_text = "\n".join(
        f"- {e.degree} in {e.field} from {e.institution} ({e.graduated}), GPA {e.gpa}"
        for e in profile.education
    )

    return f"""You are evaluating a job posting for a candidate. Score the job on two dimensions.

## Candidate Profile
Name: {profile.name}
Skills: {", ".join(profile.skills)}
Target roles: {", ".join(profile.target_roles)}
Target salary: ${profile.target_salary_min}–${profile.target_salary_max}

Work History:
{work_history_text}

Education:
{education_text}

## Job Posting
Title: {job.title}
Company: {job.company}
Location: {job.location}
Salary: {job.salary or "Not specified"}
Description:
{job.description or "Not provided"}

## Instructions
Return ONLY a JSON object with exactly these four keys:
- desirability_score: float 0.0–1.0 (how much the candidate would want this job)
- fit_score: float 0.0–1.0 (how well the candidate matches the job requirements)
- desirability_justification: string (1–2 sentences explaining desirability score)
- fit_justification: string (1–2 sentences explaining fit score)

Consider for desirability: salary vs target, remote/location fit, role alignment, company quality.
Consider for fit: required skills vs candidate skills, experience level, education requirements.

Return only the JSON object, no other text.
"""


def parse_claude_response(raw: str) -> Optional[dict]:
    """Parse Claude's JSON response. Returns None if invalid or missing keys."""
    required = {"desirability_score", "fit_score", "desirability_justification", "fit_justification"}
    try:
        data = json.loads(raw.strip())
        if not required.issubset(data.keys()):
            return None
        return data
    except (json.JSONDecodeError, AttributeError):
        return None


def score_job(
    job: Job,
    profile: UserProfile,
    config: dict[str, float],
    client: anthropic.Anthropic,
    db: Session,
) -> None:
    """Score a single job using Claude. Updates job in-place and commits."""
    prompt = build_prompt(job, profile)

    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text
    except Exception as e:
        warnings.warn(f"Claude API error for {job.job_key}: {e}")
        return

    parsed = parse_claude_response(raw)
    if parsed is None:
        warnings.warn(f"Unparseable Claude response for {job.job_key}: {raw!r}")
        return

    desirability = max(0.0, min(1.0, float(parsed["desirability_score"])))
    fit = max(0.0, min(1.0, float(parsed["fit_score"])))

    if desirability != parsed["desirability_score"]:
        warnings.warn(f"desirability_score clamped for {job.job_key}")
    if fit != parsed["fit_score"]:
        warnings.warn(f"fit_score clamped for {job.job_key}")

    final = compute_final_score(config["w1"], config["w2"], desirability, fit)

    job.desirability_score = desirability
    job.fit_score = fit
    job.final_score = final
    job.score_justification = json.dumps({
        "desirability": parsed["desirability_justification"],
        "fit": parsed["fit_justification"],
    })
    job.state = determine_state(final, config["auto_reject_threshold"], config["auto_approve_threshold"])

    db.commit()
