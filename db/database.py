from __future__ import annotations

import os

from dotenv import load_dotenv
from sqlalchemy import Column, Integer, String, Text, UniqueConstraint, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """SQLAlchemy declarative base — registry for all ORM models."""
    pass


class Config(Base):
    """Key-value application configuration store."""

    __tablename__ = "config"
    key = Column(String, primary_key=True)
    value = Column(Text)


class FieldHelp(Base):
    """Human-readable descriptions for database columns, used by the UI."""

    __tablename__ = "field_help"
    table_name = Column(String, primary_key=True)
    column_name = Column(String, primary_key=True)
    description = Column(Text, nullable=False, default="")

class PromptDefault(Base):
    """Global factory-default prompt content, one row per prompt type."""

    __tablename__ = "prompt_defaults"
    type_key = Column(String, primary_key=True)
    content = Column(Text, nullable=False, default="")


class Prompt(Base):
    """A per-profile prompt slot: active content plus an optional model override."""

    __tablename__ = "prompts"
    __table_args__ = (UniqueConstraint("profile_id", "type_key", name="uq_prompts_profile_type"),)

    id = Column(Integer, primary_key=True)
    profile_id = Column(Integer, nullable=False)
    type_key = Column(String, nullable=False)
    content = Column(Text, nullable=False, default="")
    model = Column(String, nullable=False, default="")
    updated_at = Column(String)


class Document(Base):
    """A stored, structured generated document (résumé or cover) per job.

    ``structured_json`` is the serialized Pydantic document model and is the
    source of truth. One row per (job_key, doc_type).
    """

    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("job_key", "doc_type", name="uq_documents_job_type"),
    )

    id = Column(Integer, primary_key=True)
    job_key = Column(String, nullable=False)
    doc_type = Column(String, nullable=False)  # "resume" | "cover"
    structured_json = Column(Text, nullable=False, default="{}")
    created_at = Column(String)

    @classmethod
    def fetch(cls, db: "Session", job_key: str, doc_type: str) -> "Document | None":
        """Return the stored document for (job_key, doc_type), or None."""
        return (
            db.query(cls)
            .filter_by(job_key=job_key, doc_type=doc_type)
            .first()
        )

    @classmethod
    def upsert(cls, db: "Session", job_key: str, doc_type: str, structured_json: str) -> "Document":
        """Insert or replace the document for (job_key, doc_type) and commit."""
        from datetime import datetime, timezone

        row = cls.fetch(db, job_key, doc_type)
        now = datetime.now(timezone.utc).isoformat()
        if row is None:
            row = cls(
                job_key=job_key,
                doc_type=doc_type,
                structured_json=structured_json,
                created_at=now,
            )
            db.add(row)
        else:
            row.structured_json = structured_json
            row.created_at = now
        db.commit()
        return row


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


def _migrate_ext_columns() -> None:
    """Add ext_* extraction columns to the jobs table if they do not exist."""
    ext_columns = [
        "ext_seniority", "ext_role_type", "ext_domain", "ext_work_arrangement",
        "ext_employment_type", "ext_required_skills", "ext_preferred_skills",
        "ext_tech_stack", "ext_key_responsibilities", "ext_company_signals",
    ]
    with engine.connect() as conn:
        existing = [r[1] for r in conn.execute(text("PRAGMA table_info(jobs)")).fetchall()]
        for col in ext_columns:
            if col not in existing:
                conn.execute(text(f"ALTER TABLE jobs ADD COLUMN {col} TEXT"))
        conn.commit()


def _migrate_unread_indicator_columns() -> None:
    """Add unread_indicator + last_result_error columns to jobs table if missing."""
    new_cols = [("unread_indicator", "TEXT"), ("last_result_error", "TEXT")]
    with engine.connect() as conn:
        existing = [r[1] for r in conn.execute(text("PRAGMA table_info(jobs)")).fetchall()]
        for col, typ in new_cols:
            if col not in existing:
                conn.execute(text(f"ALTER TABLE jobs ADD COLUMN {col} {typ}"))
        conn.commit()


def _migrate_pending_review_actions() -> None:
    """Add pending_review_actions column (JSON list of action names)."""
    with engine.connect() as conn:
        existing = [r[1] for r in conn.execute(text("PRAGMA table_info(jobs)")).fetchall()]
        if "pending_review_actions" not in existing:
            conn.execute(text("ALTER TABLE jobs ADD COLUMN pending_review_actions TEXT"))
        conn.commit()


def _migrate_generated_at_columns() -> None:
    """Add resume_generated_at and cover_generated_at columns to jobs table if missing."""
    new_cols = [("resume_generated_at", "TEXT"), ("cover_generated_at", "TEXT")]
    with engine.connect() as conn:
        existing = [r[1] for r in conn.execute(text("PRAGMA table_info(jobs)")).fetchall()]
        for col, typ in new_cols:
            if col not in existing:
                conn.execute(text(f"ALTER TABLE jobs ADD COLUMN {col} {typ}"))
        conn.commit()


def _migrate_flagged_column() -> None:
    """Add flagged column to jobs table if it does not exist."""
    with engine.connect() as conn:
        existing = [r[1] for r in conn.execute(text("PRAGMA table_info(jobs)")).fetchall()]
        if "flagged" not in existing:
            conn.execute(text("ALTER TABLE jobs ADD COLUMN flagged BOOLEAN NOT NULL DEFAULT 0"))
        conn.commit()


def _migrate_resume_eval_columns() -> None:
    """Add resume/cover eval columns for the refinement loop."""
    new_cols = [
        ("resume_eval_score", "REAL"),
        ("resume_eval_turns", "INTEGER"),
        ("resume_eval_log", "TEXT"),
        ("cover_eval_score", "REAL"),
        ("cover_eval_turns", "INTEGER"),
        ("cover_eval_log", "TEXT"),
    ]
    with engine.connect() as conn:
        existing = [r[1] for r in conn.execute(text("PRAGMA table_info(jobs)")).fetchall()]
        for col, typ in new_cols:
            if col not in existing:
                conn.execute(text(f"ALTER TABLE jobs ADD COLUMN {col} {typ}"))
        conn.commit()


def init_db() -> None:
    """Create all tables, run schema migrations, and seed default data."""
    import core.job   # noqa: F401 — registers Job with Base.metadata
    import core.user  # noqa: F401 — registers User with Base.metadata
    Base.metadata.create_all(bind=engine)
    _migrate_profile_name()
    _migrate_legacy_config()
    _migrate_ext_columns()
    _migrate_unread_indicator_columns()
    _migrate_pending_review_actions()
    _migrate_generated_at_columns()
    _migrate_flagged_column()
    _migrate_resume_eval_columns()
    from db.seed import seed_field_help, seed_user_profile_field_help, seed_latex_templates, seed_prompt_defaults, migrate_file_prompts_to_db
    db = SessionLocal()
    try:
        seed_field_help(db)
        seed_user_profile_field_help(db)
        seed_latex_templates(db)
        seed_prompt_defaults(db)
        migrate_file_prompts_to_db(db)
    finally:
        db.close()


def get_db():
    """FastAPI dependency that yields a database session."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
