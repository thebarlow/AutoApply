import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import Base, get_db, PromptDefault
from db.seed import PROMPT_TYPE_KEYS
from core.user import User
from web.auth import routes as auth_routes
from web.auth.identity import Claims


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    s = TestSession()
    for tk in PROMPT_TYPE_KEYS:
        s.add(PromptDefault(type_key=tk, content="x " * 20))
    s.commit()

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test")
    app.include_router(auth_routes.router)
    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setenv("ALLOWED_EMAILS", "new@x.com")
    return TestClient(app)


def _patch_claims(monkeypatch, claims):
    async def fake(provider, request):
        return claims
    monkeypatch.setattr(auth_routes, "_fetch_claims", fake)


def test_callback_provisions_and_sets_session(client, monkeypatch):
    _patch_claims(monkeypatch, Claims("google", "s1", "new@x.com", True))
    r = client.get("/auth/callback/google", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert r.headers["location"] == "/"
    me = client.get("/api/me")
    assert me.status_code == 200
    assert me.json()["email"] == "new@x.com"


def test_callback_beta_denied_redirects(client, monkeypatch):
    monkeypatch.setenv("ALLOWED_EMAILS", "other@x.com")
    _patch_claims(monkeypatch, Claims("google", "s2", "new@x.com", True))
    r = client.get("/auth/callback/google", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert "beta=closed" in r.headers["location"]
    assert client.get("/api/me").status_code == 401


def test_me_401_without_session(client):
    assert client.get("/api/me").status_code == 401


def test_logout_clears_session(client, monkeypatch):
    _patch_claims(monkeypatch, Claims("google", "s1", "new@x.com", True))
    client.get("/auth/callback/google", follow_redirects=False)
    assert client.get("/api/me").status_code == 200
    client.post("/auth/logout")
    assert client.get("/api/me").status_code == 401


def test_unknown_provider_404(client):
    assert client.get("/auth/callback/twitter", follow_redirects=False).status_code == 404
