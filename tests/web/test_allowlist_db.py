import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.database import Base, AllowedEmail
from web.auth.identity import is_allowed_email


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def test_env_allowlist_still_works(db, monkeypatch):
    monkeypatch.setenv("ALLOWED_EMAILS", "envuser@example.com")
    assert is_allowed_email(db, "envuser@example.com") is True


def test_db_allowlist_row_matches(db, monkeypatch):
    monkeypatch.setenv("ALLOWED_EMAILS", "")
    db.add(AllowedEmail(email="invited@example.com", created_at=_now()))
    db.commit()
    assert is_allowed_email(db, "invited@example.com") is True


def test_unknown_email_rejected(db, monkeypatch):
    monkeypatch.setenv("ALLOWED_EMAILS", "")
    assert is_allowed_email(db, "stranger@example.com") is False


def test_db_allowlist_case_insensitive(db, monkeypatch):
    monkeypatch.setenv("ALLOWED_EMAILS", "")
    db.add(AllowedEmail(email="Test@Example.COM", created_at=_now()))
    db.commit()
    assert is_allowed_email(db, "test@example.com") is True
