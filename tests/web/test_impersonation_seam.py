import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from db.database import Base, Account
from web.tenancy import current_profile_id


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def _req(session: dict) -> Request:
    return Request({"type": "http", "headers": [], "session": session})


def _seed(db, *, account_id, profile_id, is_admin):
    db.add(Account(id=account_id, email=f"a{account_id}@x.com", is_admin=is_admin,
                   profile_id=profile_id, created_at="2026-01-01T00:00:00+00:00",
                   credit_balance=0, credit_rate=0.0, tier="standard"))
    db.commit()


def test_admin_impersonation_returns_target(db, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    _seed(db, account_id=1, profile_id=1, is_admin=True)
    _seed(db, account_id=2, profile_id=7, is_admin=False)
    assert current_profile_id(_req({"account_id": 1, "impersonate_profile_id": 7}), db) == 7


def test_non_admin_flag_ignored(db, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    _seed(db, account_id=2, profile_id=5, is_admin=False)
    assert current_profile_id(_req({"account_id": 2, "impersonate_profile_id": 7}), db) == 5


def test_no_flag_returns_own(db, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    _seed(db, account_id=1, profile_id=1, is_admin=True)
    assert current_profile_id(_req({"account_id": 1}), db) == 1


def test_malformed_flag_ignored(db, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    _seed(db, account_id=1, profile_id=1, is_admin=True)
    assert current_profile_id(_req({"account_id": 1, "impersonate_profile_id": "abc"}), db) == 1
