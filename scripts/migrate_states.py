"""One-time migration: set all legacy job states to draft."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.database import SessionLocal
from core.job import Job

LEGACY_STATES = {"pending", "generated", "scraped", "approved", "pending_review", "failed"}


def migrate(db) -> None:
    jobs = db.query(Job).all()
    updated = 0
    for job in jobs:
        if job.state in LEGACY_STATES:
            job.state = "draft"
            updated += 1
    db.commit()
    print(f"Migrated {updated} of {len(jobs)} jobs to 'draft'.")


if __name__ == "__main__":
    db = SessionLocal()
    try:
        migrate(db)
    finally:
        db.close()
