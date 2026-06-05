from __future__ import annotations

import os
from datetime import datetime, timezone

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
        row = cls.fetch(db, job_key, doc_type)
        if row is None:
            row = cls(
                job_key=job_key,
                doc_type=doc_type,
                structured_json=structured_json,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            db.add(row)
        else:
            # Only update the content; leave created_at frozen at its original insert time.
            row.structured_json = structured_json
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


def _migrate_resume_docx_column() -> None:
    """Add resume_docx_path column to jobs table if missing."""
    with engine.connect() as conn:
        existing = [r[1] for r in conn.execute(text("PRAGMA table_info(jobs)")).fetchall()]
        if "resume_docx_path" not in existing:
            conn.execute(text("ALTER TABLE jobs ADD COLUMN resume_docx_path TEXT"))
        conn.commit()


def _migrate_ats_report_columns() -> None:
    """Add the ATS-gate report columns to jobs table if missing."""
    cols = {
        "ats_passed": "BOOLEAN",
        "ats_score": "REAL",
        "ats_report_json": "TEXT",
        "ats_checked_at": "TEXT",
    }
    with engine.connect() as conn:
        existing = [r[1] for r in conn.execute(text("PRAGMA table_info(jobs)")).fetchall()]
        for name, sqltype in cols.items():
            if name not in existing:
                conn.execute(text(f"ALTER TABLE jobs ADD COLUMN {name} {sqltype}"))
        conn.commit()


def _migrate_resume_prompt_v2() -> None:
    """Force the résumé default + all profile résumé prompts to the Phase 3a contract.

    Runs once (gated by Config key ``resume_prompt_v2``). Overwrites custom
    résumé prompt edits — required because the old free-form prompt no longer
    parses under the structured ResumeGeneration contract.
    """
    from pathlib import Path

    db = SessionLocal()
    try:
        flag = db.query(Config).filter_by(key="resume_prompt_v2").first()
        if flag and flag.value == "1":
            return
        new_content = (
            Path(__file__).parent.parent / "prompts" / "defaults" / "resume.md"
        ).read_text(encoding="utf-8")

        default = db.query(PromptDefault).filter_by(type_key="resume").first()
        if default is None:
            db.add(PromptDefault(type_key="resume", content=new_content))
        else:
            default.content = new_content
        for row in db.query(Prompt).filter_by(type_key="resume").all():
            row.content = new_content

        if flag is None:
            db.add(Config(key="resume_prompt_v2", value="1"))
        else:
            flag.value = "1"
        db.commit()
    finally:
        db.close()


def _migrate_resume_refine_prompt_v2() -> None:
    """Force the résumé-refine default + profile prompts to the Phase 3b contract.

    Runs once (gated by Config key ``resume_refine_prompt_v2``). Overwrites
    custom edits — required because the old free-form refine prompt no longer
    parses under the structured keyed-patch contract.
    """
    from pathlib import Path

    db = SessionLocal()
    try:
        flag = db.query(Config).filter_by(key="resume_refine_prompt_v2").first()
        if flag and flag.value == "1":
            return
        new_content = (
            Path(__file__).parent.parent / "prompts" / "defaults" / "resume_refine.md"
        ).read_text(encoding="utf-8")

        default = db.query(PromptDefault).filter_by(type_key="resume_refine").first()
        if default is None:
            db.add(PromptDefault(type_key="resume_refine", content=new_content))
        else:
            default.content = new_content
        for row in db.query(Prompt).filter_by(type_key="resume_refine").all():
            row.content = new_content

        if flag is None:
            db.add(Config(key="resume_refine_prompt_v2", value="1"))
        else:
            flag.value = "1"
        db.commit()
    finally:
        db.close()


def _migrate_resume_eval_prompt_v2() -> None:
    """Force the résumé-eval default + profile prompts to the present-and-relevant
    skill-coverage contract.

    Runs once (gated by Config key ``resume_eval_prompt_v2``). Overwrites custom
    edits so the eval loop enforces that skills the candidate has and the job
    wants survive generation into the résumé (mirrors the ATS gate's
    present_skill_dropped intersection one step earlier).
    """
    from pathlib import Path

    db = SessionLocal()
    try:
        flag = db.query(Config).filter_by(key="resume_eval_prompt_v2").first()
        if flag and flag.value == "1":
            return
        new_content = (
            Path(__file__).parent.parent / "prompts" / "defaults" / "resume_eval.md"
        ).read_text(encoding="utf-8")

        default = db.query(PromptDefault).filter_by(type_key="resume_eval").first()
        if default is None:
            db.add(PromptDefault(type_key="resume_eval", content=new_content))
        else:
            default.content = new_content
        for row in db.query(Prompt).filter_by(type_key="resume_eval").all():
            row.content = new_content

        if flag is None:
            db.add(Config(key="resume_eval_prompt_v2", value="1"))
        else:
            flag.value = "1"
        db.commit()
    finally:
        db.close()


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
    _migrate_resume_docx_column()
    _migrate_ats_report_columns()
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
    _migrate_resume_prompt_v2()
    _migrate_resume_refine_prompt_v2()
    _migrate_resume_eval_prompt_v2()
    _seed_ats_parse_prompt()


def _seed_ats_parse_prompt() -> None:
    """Seed the ats_parse semantic-layer prompt as a PromptDefault (idempotent).

    Kept out of PROMPT_TYPE_KEYS so it is not exposed as a per-profile prompt;
    the ATS gate loads it directly from prompt_defaults.
    """
    from pathlib import Path

    db = SessionLocal()
    try:
        if db.query(PromptDefault).filter_by(type_key="ats_parse").first():
            return
        content = (Path(__file__).parent.parent / "prompts" / "defaults" / "ats_parse.md").read_text(encoding="utf-8")
        db.add(PromptDefault(type_key="ats_parse", content=content))
        db.commit()
    finally:
        db.close()


def get_db():
    """FastAPI dependency that yields a database session."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
