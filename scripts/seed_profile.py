"""Load a profile JSON file into the user_profile table (upsert)."""
from __future__ import annotations

import argparse
import json
import sys

from sqlalchemy.orm import Session

from db.database import SessionLocal
from db.models import UserProfileModel


def seed_profile(db: Session, input_path: str) -> None:
    """Upsert profile JSON from input_path into the user_profile table."""
    with open(input_path) as f:
        data = json.load(f)

    row = db.query(UserProfileModel).first()
    if row:
        row.data = json.dumps(data)
    else:
        db.add(UserProfileModel(data=json.dumps(data)))
    db.commit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Path to profile JSON file")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        seed_profile(db, args.input)
        print(f"Profile loaded from {args.input}")
    finally:
        db.close()
