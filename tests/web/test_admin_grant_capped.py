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


def _seed_target(db, *, is_admin=False, balance=0, pid=3):
    db.add(Account(id=pid, email=f"u{pid}@x.com", is_admin=is_admin, profile_id=pid,
                   created_at="t", credit_balance=balance, credit_rate=1.0,
                   tier="standard", banned=False))
    db.commit()


def _set_remaining(monkeypatch, value):
    monkeypatch.setattr("web.routers.admin.openrouter_remaining", lambda: value)


def test_grant_success_within_cap(client, monkeypatch):
    app, db = client
    _admin_ok(app, db)
    _seed_target(db, balance=100)
    _set_remaining(monkeypatch, 20.0)  # 20000 system, allocated 100, available 19900
    r = TestClient(app).post("/api/admin/users/3/grant", json={"amount": 500})
    assert r.status_code == 200
    assert r.json()["granted"] == 500
    assert db.query(Account).filter_by(profile_id=3).first().credit_balance == 600


def test_grant_exceeds_cap_400(client, monkeypatch):
    app, db = client
    _admin_ok(app, db)
    _seed_target(db, balance=0)
    _set_remaining(monkeypatch, 0.5)  # 500 system, allocated 0, available 500
    r = TestClient(app).post("/api/admin/users/3/grant", json={"amount": 501})
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "exceeds_grant_budget"
    assert r.json()["detail"]["available"] == 500


def test_grant_unavailable_balance_409(client, monkeypatch):
    app, db = client
    _admin_ok(app, db)
    _seed_target(db)
    _set_remaining(monkeypatch, None)
    r = TestClient(app).post("/api/admin/users/3/grant", json={"amount": 10})
    assert r.status_code == 409


def test_grant_admin_target_400(client, monkeypatch):
    app, db = client
    _admin_ok(app, db)
    _seed_target(db, is_admin=True, pid=4)
    _set_remaining(monkeypatch, 20.0)
    r = TestClient(app).post("/api/admin/users/4/grant", json={"amount": 10})
    assert r.status_code == 400


def test_grant_nonpositive_400(client, monkeypatch):
    app, db = client
    _admin_ok(app, db)
    _seed_target(db)
    _set_remaining(monkeypatch, 20.0)
    r = TestClient(app).post("/api/admin/users/3/grant", json={"amount": 0})
    assert r.status_code == 400


def test_grant_unknown_profile_404(client, monkeypatch):
    app, db = client
    _admin_ok(app, db)
    _set_remaining(monkeypatch, 20.0)
    r = TestClient(app).post("/api/admin/users/999/grant", json={"amount": 10})
    assert r.status_code == 404


def test_grant_banned_target_400(client, monkeypatch):
    app, db = client
    _admin_ok(app, db)
    _seed_target(db)
    db.query(Account).filter_by(profile_id=3).first().banned = True
    db.commit()
    _set_remaining(monkeypatch, 20.0)
    r = TestClient(app).post("/api/admin/users/3/grant", json={"amount": 10})
    assert r.status_code == 400
