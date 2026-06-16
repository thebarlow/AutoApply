import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from db.database import Base, Account, Identity
from web.tenancy import current_profile_id
from web.auth.identity import _resolve_or_provision, Claims, BetaAccessDenied


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def _req(session):
    return Request({"type": "http", "headers": [], "session": session})


def _seed_acct(db, *, account_id, profile_id, banned, is_admin=False):
    db.add(Account(id=account_id, email=f"a{account_id}@x.com", is_admin=is_admin,
                   profile_id=profile_id, created_at="2026-01-01T00:00:00+00:00",
                   credit_balance=0, credit_rate=1.0, tier="standard", banned=banned))
    db.commit()


def test_seam_blocks_banned(db, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    _seed_acct(db, account_id=1, profile_id=1, banned=True)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as ei:
        current_profile_id(_req({"account_id": 1}), db)
    assert ei.value.status_code == 401


def test_seam_allows_unbanned(db, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    _seed_acct(db, account_id=1, profile_id=1, banned=False)
    assert current_profile_id(_req({"account_id": 1}), db) == 1


def test_login_blocks_banned_existing_identity(db):
    _seed_acct(db, account_id=1, profile_id=1, banned=True)
    db.add(Identity(account_id=1, provider="google", provider_subject="sub1",
                    created_at="2026-01-01T00:00:00+00:00"))
    db.commit()
    claims = Claims(provider="google", subject="sub1", email="a1@x.com",
                    email_verified=True)
    with pytest.raises(BetaAccessDenied):
        _resolve_or_provision(db, claims)


def test_login_blocks_banned_second_provider(db):
    # Banned account exists by email; login via a NEW provider must be rejected.
    _seed_acct(db, account_id=1, profile_id=1, banned=True)
    claims = Claims(provider="github", subject="gh-sub", email="a1@x.com",
                    email_verified=True)
    # email is allowlisted so we reach the email-match branch, not the allowlist gate
    import os
    os.environ["ALLOWED_EMAILS"] = "a1@x.com"
    try:
        with pytest.raises(BetaAccessDenied):
            _resolve_or_provision(db, claims)
    finally:
        os.environ.pop("ALLOWED_EMAILS", None)


def test_resolve_existing_blocks_banned(db):
    from web.auth.identity import _resolve_existing_or_raise
    _seed_acct(db, account_id=1, profile_id=1, banned=True)
    db.add(Identity(account_id=1, provider="google", provider_subject="sub1",
                    created_at="2026-01-01T00:00:00+00:00"))
    db.commit()
    claims = Claims(provider="google", subject="sub1", email="a1@x.com",
                    email_verified=True)
    with pytest.raises(BetaAccessDenied):
        _resolve_existing_or_raise(db, claims)
