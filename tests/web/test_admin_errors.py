import datetime as dt

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import Base, Account, ErrorEvent, get_db
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


def _admin_ok(app, db):
    from web.routers.admin import require_real_admin
    admin = db.query(Account).filter_by(id=1).first()
    app.dependency_overrides[require_real_admin] = lambda: admin


def _deny_admin(app):
    from web.routers.admin import require_real_admin
    def _deny():
        raise HTTPException(status_code=403, detail="admin only")
    app.dependency_overrides[require_real_admin] = _deny


def _seed(db):
    db.add(ErrorEvent(
        created_at="2026-07-23T00:00:00+00:00", last_seen="2026-07-23T00:00:00+00:00",
        count=3, level="ERROR", logger="x", message="boom", traceback="TB",
        route="/api/x", method="POST", profile_id=2, account_email="a@b.com",
        request_id="rid", fingerprint="fp1",
    ))
    db.commit()


def test_list_and_detail_include_method_and_email(client):
    c, db = client
    app = c.app
    _admin_ok(app, db)
    _seed(db)
    row = TestClient(app).get("/api/admin/errors").json()["errors"][0]
    assert row["method"] == "POST"
    assert row["account_email"] == "a@b.com"
    eid = db.query(ErrorEvent).one().id
    detail = TestClient(app).get(f"/api/admin/errors/{eid}").json()
    assert detail["method"] == "POST"
    assert detail["account_email"] == "a@b.com"


def test_list_errors_admin_only(client):
    c, db = client
    app = c.app
    _seed(db)

    _deny_admin(app)
    assert TestClient(app).get("/api/admin/errors").status_code == 403

    _admin_ok(app, db)
    resp = TestClient(app).get("/api/admin/errors")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["errors"][0]["message"] == "boom"
    assert body["errors"][0]["count"] == 3
    assert "traceback" not in body["errors"][0]


def test_detail_includes_traceback(client):
    c, db = client
    app = c.app
    _admin_ok(app, db)
    _seed(db)
    eid = db.query(ErrorEvent).one().id
    resp = TestClient(app).get(f"/api/admin/errors/{eid}")
    assert resp.status_code == 200
    assert resp.json()["traceback"] == "TB"


def test_filter_by_level(client):
    c, db = client
    app = c.app
    _admin_ok(app, db)
    _seed(db)
    resp = TestClient(app).get("/api/admin/errors?level=WARNING")
    assert resp.json()["errors"] == []


def test_clear_errors(client):
    c, db = client
    app = c.app
    _admin_ok(app, db)
    _seed(db)
    resp = TestClient(app).delete("/api/admin/errors")
    assert resp.json()["deleted"] == 1
    assert db.query(ErrorEvent).count() == 0
