import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import Base, Account, ExtensionToken
from web.auth import ext_token


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    s.add(Account(id=5, email="u@x.com", profile_id=9, created_at="t"))
    s.commit()
    yield s
    s.close()


def test_mint_stores_hash_not_raw(db):
    raw = ext_token.mint_token(db, account_id=5)
    assert raw and len(raw) > 20
    row = db.query(ExtensionToken).one()
    assert row.token_hash != raw
    assert row.token_hash == ext_token.hash_token(raw)


def test_resolve_returns_account(db):
    raw = ext_token.mint_token(db, account_id=5)
    acct = ext_token.resolve_token(db, raw)
    assert acct.id == 5
    assert db.query(ExtensionToken).one().last_used_at is not None


def test_resolve_rejects_unknown(db):
    assert ext_token.resolve_token(db, "garbage") is None


def test_resolve_rejects_revoked(db):
    raw = ext_token.mint_token(db, account_id=5)
    ext_token.revoke_token(db, raw)
    assert ext_token.resolve_token(db, raw) is None


def test_resolve_rejects_banned(db):
    raw = ext_token.mint_token(db, account_id=5)
    db.query(Account).filter_by(id=5).update({"banned": True})
    db.commit()
    assert ext_token.resolve_token(db, raw) is None
