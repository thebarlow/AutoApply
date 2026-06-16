import datetime as dt

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import Base, Account, AllowedEmail, get_db
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


def _seed_user(db, *, banned=False, is_admin=False, pid=3, email="u3@x.com"):
    db.add(Account(id=pid, email=email, is_admin=is_admin, profile_id=pid,
                   created_at="2026-01-01T00:00:00+00:00", credit_balance=0,
                   credit_rate=1.0, tier="standard", banned=banned))
    db.add(AllowedEmail(email=email, created_at="2026-01-01T00:00:00+00:00"))
    db.commit()


def test_ban_sets_flag_and_removes_allowlist(client):
    app, db = client
    _admin_ok(app, db)
    _seed_user(db)
    r = TestClient(app).post("/api/admin/users/3/access", json={"banned": True})
    assert r.status_code == 200 and r.json()["banned"] is True
    assert db.query(Account).filter_by(profile_id=3).first().banned is True
    assert db.query(AllowedEmail).filter_by(email="u3@x.com").first() is None


def test_restore_clears_flag(client):
    app, db = client
    _admin_ok(app, db)
    _seed_user(db, banned=True)
    r = TestClient(app).post("/api/admin/users/3/access", json={"banned": False})
    assert r.status_code == 200 and r.json()["banned"] is False
    assert db.query(Account).filter_by(profile_id=3).first().banned is False


def test_cannot_ban_admin(client):
    app, db = client
    _admin_ok(app, db)
    _seed_user(db, is_admin=True, pid=4, email="admin2@x.com")
    r = TestClient(app).post("/api/admin/users/4/access", json={"banned": True})
    assert r.status_code == 400


def test_access_unknown_404(client):
    app, db = client
    _admin_ok(app, db)
    r = TestClient(app).post("/api/admin/users/999/access", json={"banned": True})
    assert r.status_code == 404


def test_users_includes_banned(client):
    app, db = client
    _admin_ok(app, db)
    _seed_user(db, banned=True)
    rows = {r["email"]: r for r in TestClient(app).get("/api/admin/users").json()}
    assert rows["u3@x.com"]["banned"] is True
