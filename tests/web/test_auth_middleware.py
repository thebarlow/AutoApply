import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import StreamingResponse

from web.auth.middleware import AuthGateMiddleware


def _app(monkeypatch, production: bool):
    if production:
        monkeypatch.setenv("APP_ENV", "production")
    else:
        monkeypatch.delenv("APP_ENV", raising=False)

    app = FastAPI()
    app.add_middleware(AuthGateMiddleware)
    app.add_middleware(SessionMiddleware, secret_key="test")  # outermost: runs first

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/secret")
    def secret():
        return {"ok": True}

    @app.get("/api/events")
    async def events():
        async def gen():
            yield "a"
            yield "b"
        return StreamingResponse(gen(), media_type="text/event-stream")

    @app.post("/login")
    def login(request: __import__("fastapi").Request):
        request.session["account_id"] = 1
        return {"ok": True}

    return app


def test_noop_when_not_production(monkeypatch):
    client = TestClient(_app(monkeypatch, production=False))
    assert client.get("/api/secret").status_code == 200


def test_blocks_unauthenticated_api_in_production(monkeypatch):
    client = TestClient(_app(monkeypatch, production=True))
    assert client.get("/api/secret").status_code == 401


def test_health_exempt_in_production(monkeypatch):
    client = TestClient(_app(monkeypatch, production=True))
    assert client.get("/health").status_code == 200


def test_authenticated_api_allowed(monkeypatch):
    client = TestClient(_app(monkeypatch, production=True))
    client.post("/login")
    assert client.get("/api/secret").status_code == 200


def test_sse_streams_for_authenticated_user(monkeypatch):
    client = TestClient(_app(monkeypatch, production=True))
    client.post("/login")
    r = client.get("/api/events")
    assert r.status_code == 200
    assert r.text == "ab"
