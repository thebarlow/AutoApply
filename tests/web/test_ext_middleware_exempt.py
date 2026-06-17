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
    # Behavioral assertion is not possible here: route-level 401 (current_profile_id dep)
    # is byte-identical to the gate's 401 {"detail": "Not authenticated"}, so an HTTP
    # round-trip cannot distinguish "gate blocked" from "route auth blocked".  The
    # gate-bypass proof for stage-job in a bearer-auth context belongs in the bearer
    # tests once stage-job accepts bearer tokens.  Guard the config directly instead.
    from web.auth.middleware import _EXEMPT_PATHS
    assert "/api/scraper/stage-job" in _EXEMPT_PATHS


def test_ext_me_not_gated(prod_client):
    r = prod_client.get("/api/ext/me")
    assert r.status_code == 401
    assert r.json().get("detail") != "Not authenticated"


def test_other_api_still_gated(prod_client):
    r = prod_client.get("/api/jobs")
    assert r.status_code == 401
    assert r.json()["detail"] == "Not authenticated"
