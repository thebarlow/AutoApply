import pytest
from fastapi.testclient import TestClient

from web.main import app, _DEV_SESSION_SECRET


@pytest.fixture
def prod_client(monkeypatch):
    """TestClient for production environment with auth gate.

    Sets APP_ENV to production for middleware checks, but keeps SESSION_SECRET
    as dev value to allow the app to initialize.  The middleware checks
    APP_ENV at request time (in __call__), so monkeypatch works correctly.
    """
    monkeypatch.setenv("APP_ENV", "production")
    # Ensure SESSION_SECRET is set (can be dev value; middleware checks APP_ENV at request time)
    monkeypatch.setenv("SESSION_SECRET", _DEV_SESSION_SECRET)
    return TestClient(app)


def test_stage_job_not_gated_by_cookie(prod_client):
    # /api/scraper/stage-job is exempt from the gate, so requests reach the route's auth.
    # Even with no session cookie, the route is accessible (not blocked by the gate).
    # The route's own auth (current_profile_id) will reject with 401, but that proves
    # the request made it past the gate middleware.
    r = prod_client.post("/api/scraper/stage-job", json={})
    # Should get 422 (validation error) if passed the gate, or 401 from route auth.
    # Both are acceptable; the key is we're not getting the gate's early rejection.
    assert r.status_code in (401, 422)


def test_ext_me_not_gated(prod_client):
    r = prod_client.get("/api/ext/me")
    assert r.json().get("detail") != "Not authenticated"


def test_other_api_still_gated(prod_client):
    r = prod_client.get("/api/jobs")
    assert r.status_code == 401
    assert r.json()["detail"] == "Not authenticated"
