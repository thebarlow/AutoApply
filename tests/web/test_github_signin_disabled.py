"""GitHub sign-in was removed 2026-11-16: its OAuth routes must 404."""
from fastapi.testclient import TestClient

from web.main import app


def test_github_login_routes_404():
    client = TestClient(app, follow_redirects=False)
    assert client.get("/auth/login/github").status_code == 404
    assert client.get("/auth/callback/github").status_code == 404
    assert client.get("/auth/ext/login/github").status_code == 404


def test_google_login_still_registered():
    from web.auth.routes import _PROVIDERS
    assert _PROVIDERS == ("google",)
