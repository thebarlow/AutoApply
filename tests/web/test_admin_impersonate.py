import datetime as dt

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import Account, Base, get_db
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
    db.commit()
    app = FastAPI()
    from starlette.middleware.sessions import SessionMiddleware
    app.add_middleware(SessionMiddleware, secret_key="test")
    app.include_router(admin_router.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[current_profile_id] = lambda: 1
    return TestClient(app), db


def _admin_ok(app, db):
    from web.routers.admin import require_real_admin
    admin = db.query(Account).filter_by(id=1).first()
    app.dependency_overrides[require_real_admin] = lambda: admin


def _seed_target(db):
    db.add(Account(id=3, email="t@x.com", is_admin=False, profile_id=9,
                   created_at="2026-01-01T00:00:00+00:00", credit_balance=0,
                   credit_rate=1.0, tier="standard"))
    db.commit()


def test_start_unknown_profile_404(client):
    c, db = client
    app = c.app
    _admin_ok(app, db)
    r = TestClient(app).post("/api/admin/impersonate/start", json={"profile_id": 999})
    assert r.status_code == 404


def test_start_and_stop(client):
    c, db = client
    app = c.app
    _admin_ok(app, db)
    _seed_target(db)
    cl = TestClient(app)
    r = cl.post("/api/admin/impersonate/start", json={"profile_id": 9})
    assert r.status_code == 200 and r.json()["ok"] is True
    r2 = cl.post("/api/admin/impersonate/stop")
    assert r2.status_code == 200 and r2.json()["ok"] is True


def test_impersonate_banned_target_400(client):
    c, db = client
    app = c.app
    _admin_ok(app, db)
    _seed_target(db)
    db.query(Account).filter_by(profile_id=9).first().banned = True
    db.commit()
    r = TestClient(app).post("/api/admin/impersonate/start", json={"profile_id": 9})
    assert r.status_code == 400
