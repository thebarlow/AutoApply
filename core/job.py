from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import Boolean, Column, Float, Integer, String, Text
from sqlalchemy.orm import Session

from db.database import Base

_OUTPUTS_DIR = Path(__file__).parent.parent / "generator" / "outputs"


class JobState(str, Enum):
    """Valid states for a job in the pipeline."""

    DRAFT = "draft"
    APPLIED = "applied"
    IN_CONTACT = "in_contact"
    REJECTED = "rejected"


class Job(Base):
    """A job posting with all associated pipeline data and behavior.

    Columns cover scraped data, scores, description extraction, and artifact paths.
    All operations that read or write job columns are methods on this class.
    """

    __tablename__ = "jobs"
    __allow_unmapped__ = True
    __table_args__ = {"extend_existing": True}

    # ── Scrape data ────────────────────────────────────────────────────────────
    id = Column(Integer, primary_key=True)
    job_key = Column(String, unique=True, nullable=False)
    source = Column(String, nullable=False)
    title = Column(String)
    company = Column(String)
    location = Column(String)
    salary = Column(String)
    remote = Column(Boolean)
    description = Column(Text)
    url = Column(String, unique=True, nullable=False)
    posted_at = Column(String)
    scraped_at = Column(String, default=lambda: datetime.now(timezone.utc).isoformat())
    state = Column(String, nullable=False, default="draft")

    # ── Scores ─────────────────────────────────────────────────────────────────
    desirability_score = Column(Float)
    fit_score = Column(Float)
    final_score = Column(Float)
    score_justification = Column(Text)

    # ── Extracted description fields ───────────────────────────────────────────
    ext_seniority = Column(String)
    ext_role_type = Column(String)
    ext_domain = Column(String)
    ext_work_arrangement = Column(String)
    ext_employment_type = Column(String)
    ext_required_skills = Column(Text)
    ext_preferred_skills = Column(Text)
    ext_tech_stack = Column(Text)
    ext_key_responsibilities = Column(Text)
    ext_company_signals = Column(Text)

    # ── Artifacts ──────────────────────────────────────────────────────────────
    resume_path = Column(String)
    cover_path = Column(String)
    applied_at = Column(String)
    sheets_row_id = Column(String)

    @classmethod
    def from_scraped(cls, scraped: Any) -> "Job":
        """Construct a Job instance from a ScrapedJob object.

        Does not persist — add the returned instance to a session and commit.

        Args:
            scraped: A ScrapedJob dataclass instance.

        Returns:
            Unsaved Job instance with state set to DRAFT.
        """
        return cls(
            job_key=scraped.job_key,
            source=scraped.source,
            title=scraped.title,
            company=scraped.company,
            url=scraped.url,
            description=scraped.description,
            location=scraped.location,
            salary=scraped.salary,
            remote=scraped.remote,
            posted_at=scraped.posted_at,
            state=JobState.DRAFT.value,
        )

    @classmethod
    def save_batch(cls, scraped_jobs: list[Any], db: Session) -> int:
        """Persist a list of ScrapedJob objects, skipping URL duplicates.

        Args:
            scraped_jobs: List of ScrapedJob instances from a scraper source.
            db: SQLAlchemy session.

        Returns:
            Number of newly inserted jobs.
        """
        count = 0
        for scraped in scraped_jobs:
            if db.query(cls).filter_by(url=scraped.url).first():
                continue
            db.add(cls.from_scraped(scraped))
            count += 1
        db.commit()
        return count

    @classmethod
    def get(cls, job_key: str, db: Session) -> Optional["Job"]:
        """Fetch a single job by job_key.

        Args:
            job_key: Unique job identifier.
            db: SQLAlchemy session.

        Returns:
            Job instance, or None if not found.
        """
        return db.query(cls).filter_by(job_key=job_key).first()

    @classmethod
    def get_or_raise(cls, job_key: str, db: Session) -> "Job":
        """Fetch a single job by job_key, raising if not found.

        Args:
            job_key: Unique job identifier.
            db: SQLAlchemy session.

        Returns:
            Job instance.

        Raises:
            ValueError: If no job with that key exists.
        """
        job = cls.get(job_key, db)
        if job is None:
            raise ValueError(f"Job '{job_key}' not found")
        return job

    @classmethod
    def all_draft(cls, db: Session) -> list["Job"]:
        """Return all DRAFT jobs ordered by final_score descending.

        Args:
            db: SQLAlchemy session.

        Returns:
            List of Job instances in DRAFT state.
        """
        return (
            db.query(cls)
            .filter_by(state=JobState.DRAFT.value)
            .order_by(cls.final_score.desc())
            .all()
        )

    def set_state(self, state: JobState, db: Session) -> None:
        """Set the job's pipeline state and commit.

        Args:
            state: New JobState value.
            db: SQLAlchemy session.
        """
        self.state = state.value
        db.commit()

    def mark_applied(self, db: Session) -> None:
        """Mark this job as applied and record the timestamp.

        Sets state to APPLIED and populates applied_at with the current UTC time.

        Args:
            db: SQLAlchemy session.
        """
        self.state = JobState.APPLIED.value
        self.applied_at = datetime.now(timezone.utc).isoformat()
        db.commit()

    def serialize(self) -> dict:
        """Return a JSON-serializable dict of all job fields for the API.

        Parses score_justification JSON if stored as a string. Checks for
        generated markdown and PDF artifacts on disk.

        Returns:
            Dict with all job fields suitable for API responses.
        """
        justification = self.score_justification
        if isinstance(justification, str):
            try:
                justification = json.loads(justification)
            except (json.JSONDecodeError, TypeError):
                justification = {}
        return {
            "job_key": self.job_key,
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "salary": self.salary,
            "url": self.url,
            "description": self.description,
            "remote": self.remote,
            "state": self.state,
            "desirability_score": self.desirability_score,
            "fit_score": self.fit_score,
            "final_score": self.final_score,
            "score_justification": justification,
            "resume_path": self.resume_path,
            "cover_path": self.cover_path,
            "resume_md_exists": (_OUTPUTS_DIR / f"{self.job_key}_resume.md").exists(),
            "cover_md_exists": (_OUTPUTS_DIR / f"{self.job_key}_cover.md").exists(),
            "extraction_json_exists": bool(self.ext_required_skills or self.ext_seniority),
            "scraped_at": self.scraped_at or "",
        }
