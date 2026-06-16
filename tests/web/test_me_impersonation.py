import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from db.database import Base, Account
from web.auth.routes import api_me


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def _req(session):
    return Request({"type": "http", "headers": [], "session": session})


def _seed(db, **kw):
    db.add(Account(created_at="2026-01-01T00:00:00+00:00", credit_balance=0,
                   credit_rate=0.0, tier="standard", **kw))
    db.commit()


def test_me_impersonating_null_normally(db):
    _seed(db, id=1, email="admin@x.com", is_admin=True, profile_id=1)
    out = api_me(_req({"account_id": 1}), db)
    assert out["impersonating"] is None
    assert out["is_admin"] is True


def test_me_reports_impersonation_target(db):
    _seed(db, id=1, email="admin@x.com", is_admin=True, profile_id=1)
    _seed(db, id=2, email="victim@x.com", is_admin=False, profile_id=9)
    out = api_me(_req({"account_id": 1, "impersonate_profile_id": 9}), db)
    assert out["impersonating"] == {"profile_id": 9, "email": "victim@x.com"}


def test_me_non_admin_impersonation_ignored(db):
    _seed(db, id=2, email="user@x.com", is_admin=False, profile_id=5)
    out = api_me(_req({"account_id": 2, "impersonate_profile_id": 9}), db)
    assert out["impersonating"] is None


def test_me_malformed_impersonation_ignored(db):
    _seed(db, id=1, email="admin@x.com", is_admin=True, profile_id=1)
    out = api_me(_req({"account_id": 1, "impersonate_profile_id": "garbage"}), db)
    assert out["impersonating"] is None
