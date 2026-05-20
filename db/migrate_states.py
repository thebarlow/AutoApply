"""One-time migration: rewrite legacy job state values to the new pipeline states.

Run once from the project root:
    python -m db.migrate_states
"""
from __future__ import annotations

from sqlalchemy import text

from db.database import SessionLocal


def migrate() -> None:
    db = SessionLocal()
    try:
        legacy_count = db.execute(
            text("SELECT COUNT(*) FROM jobs WHERE state IN ('draft', 'in_contact')")
        ).scalar()
        if legacy_count == 0:
            print("No legacy states found — migration already complete or not needed.")
            return

        updated = db.execute(
            text("UPDATE jobs SET state = 'new' WHERE state = 'draft'")
        ).rowcount
        print(f"  draft -> new:        {updated} rows")

        updated = db.execute(
            text("UPDATE jobs SET state = 'contact' WHERE state = 'in_contact'")
        ).rowcount
        print(f"  in_contact -> contact: {updated} rows")

        db.commit()
        print("Migration complete.")
    finally:
        db.close()


if __name__ == "__main__":
    migrate()
