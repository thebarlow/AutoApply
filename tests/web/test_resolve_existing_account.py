import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import Base, Account, Identity
from web.auth.identity import Claims, resolve_existing_account, NoExtensionAccount


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def _acct(db, email="u@x.com", banned=False):
    a = Account(email=email, profile_id=7, created_at="t", banned=banned)
    db.add(a); db.commit()
    return a


def test_existing_identity_returns_account(db):
    a = _acct(db)
    db.add(Identity(account_id=a.id, provider="google", provider_subject="sub1", created_at="t")); db.commit()
    out = resolve_existing_account(db, Claims("google", "sub1", "u@x.com", True))
    assert out.id == a.id


def test_known_email_new_provider_links_identity(db):
    a = _acct(db)
    out = resolve_existing_account(db, Claims("github", "gh99", "u@x.com", True))
    assert out.id == a.id
    assert db.query(Identity).filter_by(provider="github", provider_subject="gh99").count() == 1


def test_unknown_email_rejected(db):
    with pytest.raises(NoExtensionAccount):
        resolve_existing_account(db, Claims("google", "subX", "nobody@x.com", True))


def test_unverified_email_rejected(db):
    _acct(db)
    with pytest.raises(NoExtensionAccount):
        resolve_existing_account(db, Claims("google", "subX", "u@x.com", False))


def test_banned_account_rejected(db):
    _acct(db, banned=True)
    with pytest.raises(NoExtensionAccount):
        resolve_existing_account(db, Claims("github", "gh1", "u@x.com", True))
