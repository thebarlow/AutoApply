from __future__ import annotations

import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from sqlalchemy import (
    Boolean,
    Column,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker, validates


class Base(DeclarativeBase):
    """SQLAlchemy declarative base — registry for all ORM models."""
    pass


class Config(Base):
    """Key-value application configuration store."""

    __tablename__ = "config"
    key = Column(String, primary_key=True)
    value = Column(Text)


class ProfileConfig(Base):
    """Per-tenant key-value settings. Composite PK (profile_id, key).

    The global ``config`` table holds infra keys (seam pointer, migration gates,
    platform LLM); anything a tenant configures lives here instead.
    """

    __tablename__ = "profile_config"
    profile_id = Column(Integer, primary_key=True)
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
        UniqueConstraint("profile_id", "job_key", "doc_type", name="uq_documents_profile_job_type"),
    )

    id = Column(Integer, primary_key=True)
    profile_id = Column(Integer, nullable=False, index=True)
    job_key = Column(String, nullable=False)
    doc_type = Column(String, nullable=False)  # "resume" | "cover"
    structured_json = Column(Text, nullable=False, default="{}")
    created_at = Column(String)

    @classmethod
    def fetch(cls, db: "Session", job_key: str, doc_type: str, profile_id: int) -> "Document | None":
        """Return the stored document for (profile_id, job_key, doc_type), or None."""
        return (
            db.query(cls)
            .filter_by(profile_id=profile_id, job_key=job_key, doc_type=doc_type)
            .first()
        )

    @classmethod
    def upsert(cls, db: "Session", job_key: str, doc_type: str, structured_json: str, profile_id: int) -> "Document":
        """Insert or replace the document for (profile_id, job_key, doc_type) and commit."""
        row = cls.fetch(db, job_key, doc_type, profile_id=profile_id)
        if row is None:
            row = cls(
                profile_id=profile_id,
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


class SkillAlias(Base):
    """Global skill synonym map. A group is all rows sharing one ``canonical``.

    ``alias_key`` is the lowercased, trimmed token; ``canonical`` is the display
    name and the group's identity. Each canonical also has a self-row
    (``alias_key == canonical.lower()``) so a group is never empty.
    """

    __tablename__ = "skill_aliases"
    profile_id = Column(Integer, primary_key=True)
    alias_key = Column(String, primary_key=True)
    canonical = Column(String, nullable=False)


class Account(Base):
    """A login identity owner. One account maps 1:1 to a tenant (user_profile)."""

    __tablename__ = "account"

    id = Column(Integer, primary_key=True)
    email = Column(String, nullable=False, unique=True)
    is_admin = Column(Boolean, nullable=False, default=False)
    profile_id = Column(Integer, ForeignKey("user_profile.id"), nullable=False, unique=True)
    created_at = Column(String, nullable=False)
    credit_balance = Column(Integer, nullable=False, default=0)
    credit_rate = Column(Float, nullable=False, default=1.0)
    tier = Column(String, nullable=False, default="standard")
    stripe_customer_id = Column(String, nullable=True)
    banned = Column(Boolean, nullable=False, default=False)


class Identity(Base):
    """An OAuth identity (provider + subject) attached to an Account."""

    __tablename__ = "identity"
    __table_args__ = (
        UniqueConstraint("provider", "provider_subject", name="uq_identity_provider_subject"),
    )

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("account.id"), nullable=False)
    provider = Column(String, nullable=False)
    provider_subject = Column(String, nullable=False)
    created_at = Column(String, nullable=False)


class ExtensionToken(Base):
    """A long-lived, revocable bearer token for the browser extension.

    Stores only the sha256 hash of the issued token; the raw value is returned
    once at mint time and never persisted.
    """

    __tablename__ = "extension_token"

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("account.id"), nullable=False)
    token_hash = Column(String, nullable=False, unique=True, index=True)
    created_at = Column(String, nullable=False)
    last_used_at = Column(String, nullable=True)
    revoked = Column(Boolean, nullable=False, default=False)


class AllowedEmail(Base):
    """Runtime allowlist entry (an admin invite). Supplements the ALLOWED_EMAILS
    env var, which remains the bootstrap allowlist."""

    __tablename__ = "allowed_email"

    id = Column(Integer, primary_key=True)
    email = Column(String, nullable=False, unique=True)
    invited_by = Column(Integer, ForeignKey("account.id"), nullable=True)
    created_at = Column(String, nullable=False)
    # Intended user type, applied to the Account when it is provisioned at first login.
    tier = Column(String, nullable=False, default="standard")
    is_admin = Column(Boolean, nullable=False, default=False)

    @validates("email")
    def _lowercase_email(self, key, value):
        return value.lower() if value else value


class CreditLedger(Base):
    """Append-only credit ledger: the reconcilable source of truth for balances.

    One row per grant or debit. Never updated or deleted. ``account.credit_balance``
    is a cached denormalization kept in step via the same transaction.
    """

    __tablename__ = "credit_ledger"

    id = Column(Integer, primary_key=True)
    profile_id = Column(Integer, nullable=False, index=True)
    delta = Column(Integer, nullable=False)            # +grant / -debit
    reason = Column(String, nullable=False)            # signup_grant|admin_grant|debit|adjustment
    action = Column(String, nullable=True)             # debits: score|generate|refine|eval|extract
    job_key = Column(String, nullable=True)
    raw_cost_usd = Column(Float, nullable=True)
    meta = Column(Text, nullable=True)                 # JSON: model, tokens, calls
    created_by = Column(Integer, nullable=True)        # account id for admin grants
    created_at = Column(String, nullable=False)


class Purchase(Base):
    """A Stripe Checkout purchase of a credit pack.

    Payment-side record linking a Checkout session to its credit grant. The
    ``credit_ledger`` remains the balance source of truth; this row tracks the
    Stripe lifecycle and enforces idempotent fulfillment via unique constraints.
    """

    __tablename__ = "purchase"

    id = Column(Integer, primary_key=True)
    profile_id = Column(Integer, nullable=False, index=True)
    stripe_session_id = Column(String, nullable=False, unique=True)
    stripe_event_id = Column(String, nullable=True, unique=True)
    price_id = Column(String, nullable=False)
    credits = Column(Integer, nullable=False)
    amount_usd = Column(Float, nullable=False)
    status = Column(String, nullable=False, default="pending")  # pending | completed
    tier = Column(String, nullable=True)  # buyer tier at purchase (audit)
    created_at = Column(String, nullable=False)


load_dotenv()


def _normalize_db_url(url: str) -> str:
    """Ensure a bare ``postgresql://`` URL uses the psycopg3 driver.

    Railway and many hosts expose ``postgresql://…``; SQLAlchemy needs
    ``postgresql+psycopg://…`` to select psycopg3. URLs that already name a
    driver (``postgresql+psycopg``, ``postgresql+psycopg2``) and non-Postgres
    URLs (e.g. SQLite) are returned unchanged.
    """
    prefix = "postgresql://"
    if url.startswith(prefix):
        return "postgresql+psycopg://" + url[len(prefix):]
    return url


DATABASE_URL = _normalize_db_url(os.getenv("DATABASE_URL", "sqlite:///auto_apply.db"))


def make_connect_args(url: str) -> dict:
    """Return driver connect args appropriate to the database dialect.

    ``check_same_thread`` is a SQLite-only pragma; passing it to other drivers
    (e.g. psycopg/Postgres) raises. Return it only for SQLite URLs.
    """
    if url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


engine = create_engine(DATABASE_URL, connect_args=make_connect_args(DATABASE_URL))
SessionLocal = sessionmaker(bind=engine)


if DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_conn, _record) -> None:
        """Enable WAL + a busy timeout so background pipeline threads don't hit
        ``database is locked``.

        The app writes from multiple threads (intake/scrape pipelines). Default
        SQLite journaling blocks readers during a write and makes a second writer
        fail immediately. WAL lets readers proceed during a write, and
        ``busy_timeout`` makes a contending writer wait for the lock instead of
        raising ``OperationalError: database is locked``.
        """
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=10000")  # ms
        cursor.close()


def init_db() -> None:
    """Bring the schema to head via Alembic, then seed idempotent default data."""
    import core.job   # noqa: F401 — registers Job with Base.metadata
    import core.user  # noqa: F401 — registers User with Base.metadata

    from pathlib import Path

    from alembic import command
    from alembic.config import Config as AlembicConfig

    alembic_cfg = AlembicConfig(str(Path(__file__).parent.parent / "alembic.ini"))
    # Make script_location absolute so upgrade works regardless of CWD.
    alembic_cfg.set_main_option(
        "script_location", str(Path(__file__).parent.parent / "alembic")
    )
    command.upgrade(alembic_cfg, "head")

    from db.events import register_tenant_guard
    register_tenant_guard()

    from db.seed import (
        seed_field_help,
        seed_user_profile_field_help,
        seed_prompt_defaults,
        migrate_file_prompts_to_db,
        seed_skill_aliases,
    )
    db = SessionLocal()
    try:
        seed_field_help(db)
        seed_user_profile_field_help(db)
        seed_prompt_defaults(db)
        seed_skill_aliases(db)
        migrate_file_prompts_to_db(db)
    finally:
        db.close()
    _seed_ats_parse_prompt()
    _seed_section_prompt_assist()
    _seed_skill_match_prompt()
    from db.migrations_data import upgrade_resume_parse_prompt
    _db = SessionLocal()
    try:
        upgrade_resume_parse_prompt(_db)
    finally:
        _db.close()


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


def _seed_section_prompt_assist() -> None:
    """Seed the section_prompt_assist prompt as a PromptDefault (idempotent).

    Kept out of PROMPT_TYPE_KEYS so it is not exposed as a per-profile prompt;
    the section-prompt draft endpoint loads it directly from prompt_defaults.
    """
    from pathlib import Path

    db = SessionLocal()
    try:
        if db.query(PromptDefault).filter_by(type_key="section_prompt_assist").first():
            return
        content = (
            Path(__file__).parent.parent / "prompts" / "defaults" / "section_prompt_assist.md"
        ).read_text(encoding="utf-8")
        db.add(PromptDefault(type_key="section_prompt_assist", content=content))
        db.commit()
    finally:
        db.close()


def _seed_skill_match_prompt() -> None:
    """Seed the skill_match prompt as a PromptDefault (idempotent).

    Kept out of PROMPT_TYPE_KEYS so it is not exposed as a per-profile prompt;
    the semantic skill matcher loads it directly from prompt_defaults.
    """
    from pathlib import Path

    db = SessionLocal()
    try:
        if db.query(PromptDefault).filter_by(type_key="skill_match").first():
            return
        content = (
            Path(__file__).parent.parent / "prompts" / "defaults" / "skill_match.md"
        ).read_text(encoding="utf-8")
        db.add(PromptDefault(type_key="skill_match", content=content))
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
