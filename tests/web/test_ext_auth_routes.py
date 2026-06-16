# tests/web/test_ext_auth_routes.py
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import Base, Account, get_db
from web.main import app
import web.auth.routes as routes
from web.auth.identity import Claims
from web.auth import ext_token

REDIR = "https://abc.chromiumapp.org/"


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    s.add(Account(id=3, email="u@x.com", profile_id=4, created_at="t"))
    s.commit()
    yield s
    s.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def client(db_session, monkeypatch):
    monkeypatch.setenv("EXTENSION_REDIRECT_URLS", REDIR)
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_ext_login_rejects_bad_redirect(client):
    r = client.get("/auth/ext/login/google?redirect_uri=https://evil.com/", follow_redirects=False)
    assert r.status_code == 400


def test_ext_callback_mints_token_for_existing_account(client, db_session, monkeypatch):
    async def fake_claims(provider, request):
        return Claims("google", "sub1", "u@x.com", True)
    monkeypatch.setattr(routes, "_fetch_claims", fake_claims)
    # simulate the session state the login route would have stashed
    with client as c:
        c.cookies.clear()
        # prime session via a request that sets it:
        # call login first (it stashes + 302s to provider; we ignore provider hop)
        c.get(f"/auth/ext/login/google?redirect_uri={REDIR}", follow_redirects=False)
        r = c.get("/auth/callback/google", follow_redirects=False)
    assert r.status_code in (302, 307)
    loc = r.headers["location"]
    assert loc.startswith(REDIR + "#token=")
    token = loc.split("#token=")[1]
    assert ext_token.resolve_token(db_session, token).id == 3


def test_ext_callback_no_account_returns_error_fragment(client, monkeypatch):
    async def fake_claims(provider, request):
        return Claims("google", "subX", "nobody@x.com", True)
    monkeypatch.setattr(routes, "_fetch_claims", fake_claims)
    with client as c:
        c.get(f"/auth/ext/login/google?redirect_uri={REDIR}", follow_redirects=False)
        r = c.get("/auth/callback/google", follow_redirects=False)
    assert r.headers["location"] == REDIR + "#error=no_account"


def test_ext_me_requires_valid_token(client, db_session):
    raw = ext_token.mint_token(db_session, account_id=3)
    ok = client.get("/api/ext/me", headers={"Authorization": f"Bearer {raw}"})
    assert ok.status_code == 200 and ok.json()["email"] == "u@x.com"
    bad = client.get("/api/ext/me", headers={"Authorization": "Bearer nope"})
    assert bad.status_code == 401


def test_ext_revoke(client, db_session):
    raw = ext_token.mint_token(db_session, account_id=3)
    r = client.post("/auth/ext/revoke", headers={"Authorization": f"Bearer {raw}"})
    assert r.status_code == 200
    assert ext_token.resolve_token(db_session, raw) is None
