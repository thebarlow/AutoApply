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
