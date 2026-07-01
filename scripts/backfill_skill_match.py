"""Backfill ext_skill_match for already-extracted jobs.

Runs the semantic skill matcher over jobs that have been extracted
(``ext_seniority`` set) but have no cached ``ext_skill_match`` yet. Idempotent:
re-running skips jobs already populated. Jobs with no extracted skills get an
empty matched set without an LLM call.
"""
from __future__ import annotations

from typing import Callable

from sqlalchemy.orm import Session

from core.job import Job
from core.user import User
from db.database import PromptDefault, SessionLocal


def backfill_skill_match(
    db: Session, profile_id: int, client_factory: Callable[[User], tuple]
) -> int:
    """Populate ext_skill_match for extracted, unmatched jobs of one profile.

    Args:
        db: Active SQLAlchemy session.
        profile_id: Tenant whose jobs to backfill.
        client_factory: Given a User, returns ``(client, model)``.

    Returns:
        Count of jobs updated.

    Raises:
        RuntimeError: If the ``skill_match`` PromptDefault row is missing.
    """
    row = db.query(PromptDefault).filter_by(type_key="skill_match").first()
    if row is None:
        raise RuntimeError("skill_match prompt not seeded — run db/init_db.py first")

    user = User.load(db, profile_id=profile_id)
    client, model = client_factory(user)

    # Only jobs that completed extraction (ext_seniority set) and have no cached match.
    jobs = (
        db.query(Job)
        .filter(Job.profile_id == profile_id)
        .filter(Job.ext_seniority.isnot(None), Job.ext_seniority != "")
        .filter(Job.ext_skill_match.is_(None))
        .all()
    )

    n = 0
    for job in jobs:
        try:
            job.match_profile_skills(user, client, model, db, row.content)
            db.commit()
            n += 1
        except Exception as exc:  # keep going — a single bad job shouldn't halt the run
            db.rollback()
            print(f"skip {job.job_key}: {exc}")
    return n


def main() -> None:
    """Backfill all profiles using the live LLM client."""
    from core.llm import get_client_for_profile

    db = SessionLocal()
    try:
        profile_ids = [pid for (pid,) in db.query(Job.profile_id).distinct().all()]
        total = 0
        for pid in profile_ids:
            # Lambda cell-binding: capture pid by value via default arg.
            total += backfill_skill_match(
                db,
                pid,
                lambda u, _pid=pid: get_client_for_profile(u, u.prompt_extraction_model),
            )
        print(f"backfilled {total} job(s)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
