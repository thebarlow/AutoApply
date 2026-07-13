import datetime as dt

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import Base, Account, get_db
from web.tenancy import current_profile_id
import web.routers.credits as credits_router


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add(Account(id=1, email="admin@x.com", is_admin=True, profile_id=1,
                   created_at=_now(), credit_rate=0.0, tier="standard"))
    db.add(Account(id=2, email="user@x.com", is_admin=False, profile_id=2,
                   created_at=_now(), credit_rate=1.0, tier="standard"))
    db.commit()
    app = FastAPI()
    app.include_router(credits_router.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[current_profile_id] = lambda: 1  # admin
    return TestClient(app), db


def test_admin_sets_tier_by_email(client):
    c, db = client
    r = c.post("/api/admin/credits/tier",
               json={"email": "user@x.com", "tier": "friends_family"})
    assert r.status_code == 200
    assert db.query(Account).filter_by(profile_id=2).one().tier == "friends_family"


def test_admin_set_tier_rejects_unknown_tier(client):
    c, _db = client
    r = c.post("/api/admin/credits/tier",
               json={"email": "user@x.com", "tier": "platinum"})
    assert r.status_code == 400


def test_non_admin_forbidden(client):
    c, _db = client
    # Admin is gated by require_real_admin (the real session account), not
    # current_profile_id; simulate a non-admin caller by overriding it to 403.
    from fastapi import HTTPException
    def _deny():
        raise HTTPException(status_code=403, detail="admin only")
    c.app.dependency_overrides[credits_router.require_real_admin] = _deny
    r = c.post("/api/admin/credits/tier",
               json={"email": "user@x.com", "tier": "beta"})
    assert r.status_code == 403
