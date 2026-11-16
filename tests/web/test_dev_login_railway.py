"""On Railway with APP_ENV unset, dev-only endpoints must stay closed.

Regression for audit H2: the old ``os.getenv("APP_ENV") == "production"``
check failed open, so a missing APP_ENV handed anyone an admin session via
POST /api/dev/login.
"""
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from web.main import app
from web.routers.dev import dev_login


@pytest.fixture
def railway_no_app_env(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")


def test_dev_login_route_404s_on_railway_without_app_env(railway_no_app_env):
    req = Request({"type": "http", "headers": [], "session": {}})
    with pytest.raises(HTTPException) as ei:
        dev_login(req, db=None)
    assert ei.value.status_code == 404


def test_dev_login_over_http_grants_no_session_on_railway(railway_no_app_env):
    client = TestClient(app)
    r = client.post("/api/dev/login")
    # The auth gate (now also fail-closed) rejects first; either way no session.
    assert r.status_code in (401, 404)
    assert "session" not in r.cookies
    assert client.get("/api/me").status_code == 401
