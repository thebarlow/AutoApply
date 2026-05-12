from __future__ import annotations

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from db.models import Base

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///auto_apply.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)


def _migrate_profile_name() -> None:
    """Add name column to user_profile table if it does not exist."""
    with engine.connect() as conn:
        cols = [r[1] for r in conn.execute(text("PRAGMA table_info(user_profile)")).fetchall()]
        if "name" not in cols:
            conn.execute(text("ALTER TABLE user_profile ADD COLUMN name TEXT DEFAULT 'Default'"))
            conn.commit()


def init_db() -> None:
    """Create all tables and run schema migrations."""
    Base.metadata.create_all(bind=engine)
    _migrate_profile_name()
    # Seed field help descriptions for any existing DB (no-op if already present)
    from db.seed import seed_field_help  # local import avoids circular at module level
    db = SessionLocal()
    try:
        seed_field_help(db)
    finally:
        db.close()


def get_db():
    """FastAPI dependency that yields a database session."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
