from __future__ import annotations

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """SQLAlchemy declarative base — registry for all ORM models."""
    pass

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


def _migrate_legacy_config() -> None:
    """One-time migration: port old llm_providers and template paths into the new schema."""
    import json
    import uuid

    _LLM_BASE_URLS = {
        "openrouter": "https://openrouter.ai/api/v1",
        "anthropic": "https://api.anthropic.com/v1",
        "openai": "https://api.openai.com/v1",
        "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    }
    _BASE_URL_TO_TYPE = {v: k for k, v in _LLM_BASE_URLS.items()}

    from db.models import Config

    db = SessionLocal()
    try:
        def _get(key: str) -> str:
            row = db.query(Config).filter_by(key=key).first()
            return row.value if row else ""

        def _set(key: str, value: str) -> None:
            row = db.query(Config).filter_by(key=key).first()
            if row:
                row.value = value
            else:
                db.add(Config(key=key, value=value))
            db.commit()

        # --- LLM providers ---
        named_raw = _get("named_providers")
        named = json.loads(named_raw) if named_raw else []
        if not named:
            old_raw = _get("llm_providers")
            old_providers = json.loads(old_raw) if old_raw else []
            if old_providers:
                migrated = []
                for p in old_providers:
                    provider_type = _BASE_URL_TO_TYPE.get(p.get("base_url", ""), "openrouter")
                    migrated.append({
                        "id": uuid.uuid4().hex,
                        "name": p.get("name", provider_type),
                        "provider_type": provider_type,
                    })
                _set("named_providers", json.dumps(migrated))
                print(f"[migration] Ported {len(migrated)} LLM provider(s) to named_providers.")

        # --- LaTeX template paths ---
        latex_raw = _get("latex_templates")
        latex = json.loads(latex_raw) if latex_raw else []
        if not latex:
            entries = []
            for key, label in (("resume_template_path", "Resume"), ("cover_template_path", "Cover Letter")):
                path = _get(key)
                if path:
                    entries.append({"id": uuid.uuid4().hex, "name": label, "path": path})
            if entries:
                _set("latex_templates", json.dumps(entries))
                print(f"[migration] Ported {len(entries)} LaTeX template path(s) to latex_templates.")
    finally:
        db.close()


def init_db() -> None:
    """Create all tables and run schema migrations."""
    Base.metadata.create_all(bind=engine)
    _migrate_profile_name()
    _migrate_legacy_config()
    # Seed field help descriptions for any existing DB (no-op if already present)
    from db.seed import seed_field_help, seed_user_profile_field_help, seed_latex_templates  # local import avoids circular at module level
    db = SessionLocal()
    try:
        seed_field_help(db)
        seed_user_profile_field_help(db)
        seed_latex_templates(db)
    finally:
        db.close()


def get_db():
    """FastAPI dependency that yields a database session."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
