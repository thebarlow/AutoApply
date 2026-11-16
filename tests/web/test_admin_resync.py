"""Account.is_admin is re-derived on every login (audit L6).

Sources of truth: ADMIN_EMAILS (env) OR an admin-created invite with is_admin.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.database import Account, AllowedEmail, Base, Identity
from web.auth.identity import (
    Claims,
    resolve_existing_account,
    resolve_or_provision_account,
)

EMAIL = "pat@x.com"


@pytest.fixture
def db(monkeypatch):
    monkeypatch.delenv("ADMIN_EMAILS", raising=False)
    monkeypatch.delenv("ALLOWED_EMAILS", raising=False)
    monkeypatch.setenv("CREDIT_DEFAULT_RATE", "1.0")
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def _seed(db, *, is_admin, rate=1.0, invite_admin=None):
    acct = Account(id=5, email=EMAIL, is_admin=is_admin, profile_id=5,
                   created_at="t", credit_balance=0, credit_rate=rate,
                   tier="standard", banned=False)
    db.add(acct)
    db.add(Identity(account_id=5, provider="google", provider_subject="sub",
                    created_at="t"))
    if invite_admin is not None:
        db.add(AllowedEmail(email=EMAIL, created_at="t", tier="standard",
                            is_admin=invite_admin))
    db.commit()
    return acct


def _login(db):
    return resolve_or_provision_account(
        db, Claims(provider="google", subject="sub", email=EMAIL, email_verified=True))


def test_promoted_when_added_to_admin_emails(db, monkeypatch):
    _seed(db, is_admin=False)
    monkeypatch.setenv("ADMIN_EMAILS", EMAIL)
    assert _login(db).is_admin is True


def test_demoted_when_removed_from_admin_emails(db):
    _seed(db, is_admin=True, rate=0.0)
    acct = _login(db)
    assert acct.is_admin is False
    # admin rate 0 must not survive demotion as free usage
    assert acct.credit_rate == 1.0


def test_demotion_keeps_nonzero_custom_rate(db):
    _seed(db, is_admin=True, rate=2.5)
    assert _login(db).credit_rate == 2.5


def test_invite_admin_not_demoted_without_env(db):
    _seed(db, is_admin=True, rate=0.0, invite_admin=True)
    acct = _login(db)
    assert acct.is_admin is True
    assert acct.credit_rate == 0.0


def test_invite_revoked_admin_demoted(db):
    # Admin re-invited the user with is_admin=False -> demote on next login.
    _seed(db, is_admin=True, invite_admin=False)
    assert _login(db).is_admin is False


def test_invite_admin_flag_promotes(db):
    _seed(db, is_admin=False, invite_admin=True)
    assert _login(db).is_admin is True


def test_env_admin_case_insensitive(db, monkeypatch):
    _seed(db, is_admin=False)
    monkeypatch.setenv("ADMIN_EMAILS", "Pat@X.com")
    assert _login(db).is_admin is True


def test_extension_login_also_resyncs(db):
    _seed(db, is_admin=True)
    acct = resolve_existing_account(
        db, Claims(provider="google", subject="sub", email=EMAIL, email_verified=True))
    assert acct.is_admin is False


def test_new_provider_link_resyncs(db, monkeypatch):
    _seed(db, is_admin=False)
    monkeypatch.setenv("ADMIN_EMAILS", EMAIL)
    acct = resolve_or_provision_account(
        db, Claims(provider="github", subject="gh", email=EMAIL, email_verified=True))
    assert acct.is_admin is True
