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
    with engine.connect() as conn:
        cols = [r[1] for r in conn.execute(text("PRAGMA table_info(user_profile)")).fetchall()]
        if "name" not in cols:
            conn.execute(text("ALTER TABLE user_profile ADD COLUMN name TEXT NOT NULL DEFAULT 'Default'"))
            conn.commit()


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _migrate_profile_name()


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
