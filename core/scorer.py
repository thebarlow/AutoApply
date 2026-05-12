"""Job scorer: scores SCRAPED jobs using the configured LLM and transitions their state."""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from typing import Any, Optional

from sqlalchemy.orm import Session

from core.llm import get_openai_client
from core.types import JobState, UserProfile, WorkHistoryEntry, EducationEntry, ProjectEntry
from db.database import SessionLocal
from db.models import Config, Job, UserProfileModel


def compute_final_score(w1: float, w2: float, desirability: float, fit: float) -> float:
    """Compute weighted final score, clamped to [0.0, 1.0]."""
    return max(0.0, min(1.0, w1 * desirability + w2 * fit))



def load_user_profile(db: Session) -> UserProfile:
    """Load UserProfile from DB, respecting the active profile setting."""
    row = None
    active_raw = db.query(Config).filter_by(key="active_profile_id").first()
    if active_raw and active_raw.value:
        try:
            profile_id = int(active_raw.value)
        except (ValueError, TypeError):
            print(
                f"active_profile_id config value is not a valid integer: {active_raw.value!r}",
                file=sys.stderr,
            )
            sys.exit(1)
        row = db.query(UserProfileModel).filter_by(id=profile_id).first()

    if row is None:
        row = db.query(UserProfileModel).first()

    if not row:
        if active_raw and active_raw.value:
            print(
                f"Profile with id={active_raw.value} not found. Update active_profile_id via /config.",
                file=sys.stderr,
            )
        else:
            print("No user profile found. Add one via /config.", file=sys.stderr)
        sys.exit(1)

    import dataclasses as _dc
    data = json.loads(row.data)
    data["work_history"] = [WorkHistoryEntry(**e) for e in data.get("work_history", [])]
    data["education"] = [EducationEntry(**e) for e in data.get("education", [])]
    data["projects"] = [ProjectEntry(**e) for e in data.get("projects", [])]
    _profile_fields = {f.name for f in _dc.fields(UserProfile)}
    return UserProfile(**{k: v for k, v in data.items() if k in _profile_fields})


def load_config(db: Session) -> dict[str, float]:
    """Load scoring weights and thresholds from the config table."""
    keys = ["w1", "w2", "auto_reject_threshold", "auto_approve_threshold"]
    result = {}
    for key in keys:
        row = db.query(Config).filter_by(key=key).first()
        result[key] = float(row.value) if row else 0.5
    return result


def build_prompt(job: Job, profile: UserProfile) -> str:
    """Build the scoring prompt for a single job."""
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
    """Parse LLM JSON response. Returns None if invalid or missing keys."""
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
    client: Any,
    model: str,
    db: Session,
) -> None:
    """Score a single job using the LLM. Updates job in-place and commits."""
    prompt = build_prompt(job, profile)

    try:
        response = client.chat.completions.create(
            model=model,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.choices[0].message.content
    except Exception as e:
        warnings.warn(f"LLM API error for {job.job_key}: {e}")
        return

    parsed = parse_claude_response(raw)
    if parsed is None:
        warnings.warn(f"Unparseable LLM response for {job.job_key}: {raw!r}")
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
    db.commit()


def run_scorer(
    db: Session,
    client: Optional[Any] = None,
    model: Optional[str] = None,
    job_key: Optional[str] = None,
) -> None:
    """Score all SCRAPED jobs, or a single job if job_key is provided."""
    if client is None or model is None:
        client, model = get_openai_client(db)

    profile = load_user_profile(db)
    config = load_config(db)

    if job_key:
        jobs = db.query(Job).filter_by(job_key=job_key).all()
    else:
        jobs = db.query(Job).filter_by(state=JobState.DRAFT).all()

    if not jobs:
        print("No DRAFT jobs found.")
        return

    for job in jobs:
        score_job(job, profile, config, client, model, db)
        db.refresh(job)
        score_str = f"{job.final_score:.2f}" if job.final_score is not None else "N/A"
        print(f"[{job.state.upper()}] {job.job_key} (final={score_str})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Score SCRAPED jobs using the configured LLM.")
    parser.add_argument("--job-key", help="Score a single job by key")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        run_scorer(db, job_key=args.job_key)
    finally:
        db.close()
