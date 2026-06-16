import datetime as dt

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import Base, Account, Purchase, get_db
from web.tenancy import current_profile_id
import web.routers.admin as admin_router


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
    app.include_router(admin_router.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[current_profile_id] = lambda: 1  # admin
    return TestClient(app), db


def _seed_extra_user(db):
    db.add(Account(id=3, email="user3@x.com", is_admin=False, profile_id=3,
                   created_at="2026-01-01T00:00:00+00:00", credit_balance=4200,
                   credit_rate=1.0, tier="standard"))
    db.add(Purchase(profile_id=3, stripe_session_id="cs_3", price_id="price_x",
                    credits=1000, amount_usd=10.0, status="completed",
                    created_at="2026-02-01T00:00:00+00:00"))
    db.commit()


def _admin_ok(app, db):
    from web.routers.admin import require_real_admin
    admin = db.query(Account).filter_by(id=1).first()
    app.dependency_overrides[require_real_admin] = lambda: admin


def test_users_requires_admin(client):
    c, _db = client
    app = c.app
    from fastapi import HTTPException
    from web.routers.admin import require_real_admin
    def _deny():
        raise HTTPException(status_code=403, detail="admin only")
    app.dependency_overrides[require_real_admin] = _deny
    r = TestClient(app).get("/api/admin/users")
    assert r.status_code == 403


def test_users_lists_accounts(client):
    c, db = client
    app = c.app
    _admin_ok(app, db)
    _seed_extra_user(db)
    r = TestClient(app).get("/api/admin/users")
    assert r.status_code == 200
    rows = {row["email"]: row for row in r.json()}
    assert rows["user3@x.com"]["tier"] == "standard"
    assert rows["user3@x.com"]["credits"] == 4200
    assert rows["user3@x.com"]["profile_id"] == 3
    assert rows["user3@x.com"]["is_admin"] is False


def test_user_purchases(client):
    c, db = client
    app = c.app
    _admin_ok(app, db)
    _seed_extra_user(db)
    r = TestClient(app).get("/api/admin/users/3/purchases")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["stripe_session_id"] == "cs_3"
    assert body[0]["credits"] == 1000
