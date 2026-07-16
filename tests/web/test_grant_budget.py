import datetime as dt

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import Base, Account, get_db
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
    return app, db


def _admin_ok(app, db):
    from web.routers.admin import require_real_admin
    admin = db.query(Account).filter_by(id=1).first()
    app.dependency_overrides[require_real_admin] = lambda: admin


def _seed_users(db):
    db.add(Account(id=3, email="u3@x.com", is_admin=False, profile_id=3,
                   created_at="t", credit_balance=100, credit_rate=1.0,
                   tier="standard", banned=False))
    db.add(Account(id=4, email="u4@x.com", is_admin=False, profile_id=4,
                   created_at="t", credit_balance=50, credit_rate=1.0,
                   tier="standard", banned=False))
    db.commit()


def test_budget_available(client, monkeypatch):
    app, db = client
    _admin_ok(app, db)
    _seed_users(db)
    monkeypatch.setattr("web.routers.admin.openrouter_remaining", lambda: 20.0)
    r = TestClient(app).get("/api/admin/grant-budget")
    assert r.status_code == 200
    b = r.json()
    # unit_usd() == 0.02 -> system_credits = round(remaining / 0.02)
    assert b["system_credits"] == 1000
    assert b["allocated"] == 150
    assert b["available"] == 850


def test_budget_unavailable(client, monkeypatch):
    app, db = client
    _admin_ok(app, db)
    _seed_users(db)
    monkeypatch.setattr("web.routers.admin.openrouter_remaining", lambda: None)
    r = TestClient(app).get("/api/admin/grant-budget")
    b = r.json()
    assert b["system_credits"] is None
    assert b["available"] is None
    assert b["allocated"] == 150
