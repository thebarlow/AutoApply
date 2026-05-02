"""One-time migration: map retired job states to their new equivalents."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.database import SessionLocal
from db.models import Job

RETIRED_TO_PENDING = {"scraped", "scored", "pending_review", "approved", "generated", "rejected"}

def migrate(db) -> None:
    jobs = db.query(Job).all()
    updated = 0
    for job in jobs:
        if job.state in RETIRED_TO_PENDING:
            job.state = "pending"
            updated += 1
    db.commit()
    print(f"Migrated {updated} of {len(jobs)} jobs to 'pending'.")

if __name__ == "__main__":
    db = SessionLocal()
    try:
        migrate(db)
    finally:
        db.close()
