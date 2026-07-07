"""Seed data for brand-new profiles.

A single demo job is inserted when a profile is first created so the onboarding
tour (and the empty dashboard) have something to show without the user having to
paste a posting first.
"""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

_DEMO_DESCRIPTION = """\
Acme Corp is hiring a Senior Python Engineer to build and scale our data
platform. You'll design REST APIs with FastAPI, model data in PostgreSQL, and
ship services in Docker to our cloud environment.

What you'll do:
- Design and build backend services and APIs (Python, FastAPI).
- Own data models and migrations (PostgreSQL, SQLAlchemy).
- Integrate LLM-powered features into the product.
- Collaborate across the team using CI/CD and code review.

What we're looking for:
- Strong Python and REST API experience.
- Comfort with SQL databases and containerized deployment.
- Bonus: experience with LLMs, React, or cloud platforms.

This is a demo job added to help you explore the app — feel free to delete it.
"""


def seed_demo_job(db: Session, profile_id: int) -> None:
    """Insert a one-off demo job for a new profile (idempotent by URL).

    Best-effort: any failure is swallowed and rolled back so profile creation is
    never blocked by seeding.

    Args:
        db: SQLAlchemy session.
        profile_id: The newly created profile's id.
    """
    from scraper.base import ScrapedJob
    from core.job import Job

    demo = ScrapedJob(
        source="demo",
        job_key=f"demo_welcome_{profile_id}",
        title="Senior Python Engineer (Demo)",
        company="Acme Corp",
        url=f"demo://welcome-{profile_id}",
        description=_DEMO_DESCRIPTION,
        location="Remote",
        salary="$150,000 – $180,000",
        remote=True,
    )
    try:
        inserted = Job.save_batch_returning([demo], db, profile_id)
        if inserted:
            # Pre-score it so the tour's scoring step has something to show
            # (avoids an LLM call on a brand-new profile).
            job = inserted[0]
            job.fit_score = 0.85
            job.desirability_score = 0.80
            job.final_score = 0.82
            job.score_justification = json.dumps({
                "fit": "Strong match — your Python, FastAPI, and PostgreSQL experience "
                       "lines up directly with the core requirements.",
                "desirability": "Remote, a competitive salary, and LLM-focused work make "
                                "this an appealing role.",
            })
            db.commit()
    except Exception:
        db.rollback()
