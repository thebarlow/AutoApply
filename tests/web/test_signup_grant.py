from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.database import Base, Account, CreditLedger, AllowedEmail
from core.user import User
import web.auth.identity as identity


def _db():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    db.add(User(id=1, name="T", data="{}"))
    db.commit()
    return db


def test_standard_signup_gets_no_free_units():
    # Open signups (2026-11-16): standard accounts start at 0; free use is BYOK.
    db = _db()
    claims = identity.Claims(
        provider="google", subject="sub-1", email="new@x.c", email_verified=True
    )
    acct = identity._provision_account(db, email="new@x.c", is_admin=False, claims=claims)

    assert acct.credit_balance == 0
    assert (
        db.query(CreditLedger)
        .filter_by(reason="signup_grant", profile_id=acct.profile_id)
        .first()
    ) is None


def test_beta_invite_signup_gets_200_units():
    db = _db()
    db.add(AllowedEmail(email="beta@x.c", tier="beta", created_at="2026-01-01T00:00:00+00:00"))
    db.commit()
    claims = identity.Claims(
        provider="google", subject="sub-beta", email="beta@x.c", email_verified=True
    )
    acct = identity._provision_account(db, email="beta@x.c", is_admin=False, claims=claims)

    assert acct.tier == "beta"
    assert acct.credit_balance == 200
    grant = (
        db.query(CreditLedger)
        .filter_by(reason="signup_grant", profile_id=acct.profile_id)
        .first()
    )
    assert grant is not None and grant.delta == 200


def test_provision_account_admin_gets_zero_rate():
    db = _db()
    claims = identity.Claims(
        provider="google", subject="sub-2", email="admin@x.c", email_verified=True
    )
    acct = identity._provision_account(db, email="admin@x.c", is_admin=True, claims=claims)

    assert acct.credit_rate == 0.0
    assert acct.credit_balance == 0


def test_default_rate_defaults_to_one(monkeypatch):
    from core.credits import default_rate
    monkeypatch.delenv("CREDIT_DEFAULT_RATE", raising=False)
    assert default_rate() == 1.0


def test_provision_account_is_standard_tier_rate_one(monkeypatch):
    monkeypatch.delenv("CREDIT_DEFAULT_RATE", raising=False)
    db = _db()
    claims = identity.Claims(
        provider="google", subject="sub-9", email="std@x.c", email_verified=True
    )
    acct = identity._provision_account(db, email="std@x.c", is_admin=False, claims=claims)
    assert acct.tier == "standard"
    assert acct.credit_rate == 1.0
