import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError

from db.database import Base, Account, Identity
from core.user import User


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def _profile(db, pid=1):
    db.add(User(id=pid, name="P", data="{}"))
    db.commit()
    return pid


def test_account_links_to_profile(db):
    _profile(db, 1)
    acct = Account(email="a@x.com", is_admin=False, profile_id=1, created_at="t")
    db.add(acct)
    db.commit()
    assert acct.id is not None


def test_identity_provider_subject_unique(db):
    _profile(db, 1)
    acct = Account(email="a@x.com", is_admin=False, profile_id=1, created_at="t")
    db.add(acct)
    db.commit()
    db.add(Identity(account_id=acct.id, provider="google", provider_subject="s1", created_at="t"))
    db.commit()
    db.add(Identity(account_id=acct.id, provider="google", provider_subject="s1", created_at="t"))
    with pytest.raises(IntegrityError):
        db.commit()


from db.database import PromptDefault
from db.seed import PROMPT_TYPE_KEYS
from web.auth.identity import (
    Claims,
    resolve_or_provision_account,
    BetaAccessDenied,
)


def _seed_prompt_defaults(db):
    for tk in PROMPT_TYPE_KEYS:
        db.add(PromptDefault(type_key=tk, content="x " * 20))
    db.commit()


def _claims(provider="google", subject="s1", email="new@x.com", verified=True):
    return Claims(provider=provider, subject=subject, email=email, email_verified=verified)


def test_unverified_email_denied(db, monkeypatch):
    monkeypatch.setenv("ALLOWED_EMAILS", "new@x.com")
    with pytest.raises(BetaAccessDenied):
        resolve_or_provision_account(db, _claims(verified=False))


def test_non_allowlisted_denied(db, monkeypatch):
    monkeypatch.setenv("ALLOWED_EMAILS", "other@x.com")
    monkeypatch.delenv("ADMIN_EMAILS", raising=False)
    with pytest.raises(BetaAccessDenied):
        resolve_or_provision_account(db, _claims(email="new@x.com"))


def test_allowlisted_provisions_account_profile_and_prompts(db, monkeypatch):
    monkeypatch.setenv("ALLOWED_EMAILS", "new@x.com")
    monkeypatch.delenv("ADMIN_EMAILS", raising=False)
    _seed_prompt_defaults(db)
    acct = resolve_or_provision_account(db, _claims())
    assert acct.email == "new@x.com"
    assert acct.is_admin is False
    from db.database import Prompt
    assert db.query(User).filter_by(id=acct.profile_id).first() is not None
    assert db.query(Prompt).filter_by(profile_id=acct.profile_id).count() == len(PROMPT_TYPE_KEYS)


def test_returning_identity_returns_same_account(db, monkeypatch):
    monkeypatch.setenv("ALLOWED_EMAILS", "new@x.com")
    _seed_prompt_defaults(db)
    a1 = resolve_or_provision_account(db, _claims())
    a2 = resolve_or_provision_account(db, _claims())
    assert a1.id == a2.id
    from db.database import Identity
    assert db.query(Identity).count() == 1


def test_link_by_email_attaches_second_provider(db, monkeypatch):
    monkeypatch.setenv("ALLOWED_EMAILS", "new@x.com")
    _seed_prompt_defaults(db)
    a1 = resolve_or_provision_account(db, _claims(provider="google", subject="g1"))
    a2 = resolve_or_provision_account(db, _claims(provider="github", subject="h1"))
    assert a1.id == a2.id
    assert a1.profile_id == a2.profile_id
    from db.database import Identity
    assert db.query(Identity).count() == 2


def test_admin_bypasses_allowlist_and_claims_profile_1(db, monkeypatch):
    monkeypatch.delenv("ALLOWED_EMAILS", raising=False)
    monkeypatch.setenv("ADMIN_EMAILS", "owner@x.com")
    _profile(db, 1)
    _seed_prompt_defaults(db)
    acct = resolve_or_provision_account(db, _claims(email="owner@x.com", subject="o1"))
    assert acct.is_admin is True
    assert acct.profile_id == 1


def test_second_admin_gets_fresh_profile(db, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "owner@x.com,owner2@x.com")
    _profile(db, 1)
    _seed_prompt_defaults(db)
    a1 = resolve_or_provision_account(db, _claims(email="owner@x.com", subject="o1"))
    a2 = resolve_or_provision_account(db, _claims(email="owner2@x.com", subject="o2"))
    assert a1.profile_id == 1
    assert a2.profile_id != 1


def test_concurrent_provision_race_recovers(db, monkeypatch):
    """If a concurrent login wins the provisioning race, the loser's commit hits
    a unique-constraint violation; resolve must roll back and return the existing
    account rather than raising IntegrityError."""
    import web.auth.identity as identity_mod
    from db.database import Account

    monkeypatch.setenv("ALLOWED_EMAILS", "new@x.com")
    _seed_prompt_defaults(db)

    # Simulate the winner having already created the account+identity.
    db.add(User(id=2, name="New User", data="{}"))
    db.add(Account(id=1, email="new@x.com", is_admin=False, profile_id=2, created_at="t"))
    db.flush()
    from db.database import Identity
    db.add(Identity(account_id=1, provider="google", provider_subject="s1", created_at="t"))
    db.commit()

    # Force the inner path to behave as if it raced and failed on commit.
    def boom(_db, _claims):
        raise IntegrityError("dup", None, Exception())

    from sqlalchemy.exc import IntegrityError
    monkeypatch.setattr(identity_mod, "_resolve_or_provision", boom)

    acct = resolve_or_provision_account(db, _claims())
    assert acct.id == 1
    assert acct.profile_id == 2
