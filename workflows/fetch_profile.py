"""Fetch the local user profile from auto_apply.db for job-vs-candidate comparison.

Reuses core.user.User.load() (JSON-blob hydration, legacy-tree migration, etc.)
against a locally-created engine/session — not the app's DATABASE_URL-resolving
session factory — so this stays a standalone local script per the workflows/
convention, while avoiding re-implementing User's hydration logic in raw SQL.

Usage:
    python -m workflows.fetch_profile
    python -m workflows.fetch_profile --profile-id 3 --out workflows/output/profile.json
"""
from __future__ import annotations

import argparse
import dataclasses
import json
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from core.user import User

_LOCAL_URL = "sqlite:///auto_apply.db"
_DEFAULT_OUT = Path("workflows/output/profile.json")


def fetch_profile(engine, profile_id: int | None) -> dict:
    """Load and serialize the fields relevant to matching a candidate against a job."""
    with Session(engine) as db:
        user = User.load(db, profile_id=profile_id)
        return {
            "profile_id": user.id,
            "name": f"{user.first_name} {user.last_name}".strip(),
            "hero": user.hero,
            "email": user.email,
            "phone": user.phone,
            "linkedin": user.linkedin,
            "github": user.github,
            "website": user.website,
            "location": user.location,
            "skills": user.skills,
            "work_history": [dataclasses.asdict(e) for e in user.work_history],
            "education": [dataclasses.asdict(e) for e in user.education],
            "projects": [dataclasses.asdict(e) for e in user.projects],
            "target_roles": user.target_roles,
            "target_salary_min": user.target_salary_min,
            "target_salary_max": user.target_salary_max,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile-id", type=int, default=None, help="Explicit profile id; defaults to the first row.")
    parser.add_argument("--out", type=Path, default=_DEFAULT_OUT)
    args = parser.parse_args()

    engine = create_engine(_LOCAL_URL)
    profile = fetch_profile(engine, args.profile_id)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(profile, indent=2), encoding="utf-8")

    print(f"fetched profile id={profile['profile_id']} ({profile['name'] or 'unnamed'}) -> {args.out}")


if __name__ == "__main__":
    main()
