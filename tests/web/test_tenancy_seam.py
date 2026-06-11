import pytest
from types import SimpleNamespace
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.database import Base, Account
from core.user import User
from web.tenancy import current_profile_id


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def _request(session):
    return SimpleNamespace(session=session)


def test_dev_stub_when_not_production(db, monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    assert current_profile_id(request=_request({}), db=db) == 1


def test_production_resolves_session_account(db, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    db.add(User(id=5, name="P", data="{}"))
    db.add(Account(id=9, email="a@x.com", is_admin=False, profile_id=5, created_at="t"))
    db.commit()
    assert current_profile_id(request=_request({"account_id": 9}), db=db) == 5


def test_production_no_session_401(db, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(HTTPException) as exc:
        current_profile_id(request=_request({}), db=db)
    assert exc.value.status_code == 401
