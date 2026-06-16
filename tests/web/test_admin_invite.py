import datetime as dt
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import Base, Account, AllowedEmail, get_db
from web.tenancy import current_profile_id
import web.routers.credits as credits_router
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


def test_non_admin_forbidden(client):
    c, _db = client
    c.app.dependency_overrides[current_profile_id] = lambda: 2  # non-admin
    r = c.post("/api/admin/invite", json={"email": "new@example.com"})
    assert r.status_code == 403


def test_invite_normalizes_and_emails(client):
    c, db = client
    with patch("web.routers.admin.send_invite", return_value=True) as m:
        r = c.post("/api/admin/invite", json={"email": "New@Example.com"})
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "new@example.com"
    assert body["already_invited"] is False
    assert body["emailed"] is True
    m.assert_called_once_with("new@example.com")
    rows = db.query(AllowedEmail).filter_by(email="new@example.com").all()
    assert len(rows) == 1


def test_invite_idempotent(client):
    c, db = client
    with patch("web.routers.admin.send_invite", return_value=False):
        c.post("/api/admin/invite", json={"email": "dup@example.com"})
        r = c.post("/api/admin/invite", json={"email": "dup@example.com"})
    assert r.status_code == 200
    assert r.json()["already_invited"] is True
    rows = db.query(AllowedEmail).filter_by(email="dup@example.com").all()
    assert len(rows) == 1


def test_invite_rejects_malformed_email(client):
    c, _db = client  # fixture yields (TestClient, db); client is admin-authed
    for bad in ["nope", "@example.com", "user@", "user@nodot", "user@@example.com"]:
        r = c.post("/api/admin/invite", json={"email": bad})
        assert r.status_code == 400


def test_list_invites(client):
    c, _db = client
    with patch("web.routers.admin.send_invite", return_value=True):
        c.post("/api/admin/invite", json={"email": "listed@example.com"})
    r = c.get("/api/admin/invites")
    assert r.status_code == 200
    emails = [row["email"] for row in r.json()]
    assert "listed@example.com" in emails
