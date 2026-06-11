import base64

from fastapi import FastAPI
from fastapi.testclient import TestClient

from web.auth_gate import BasicAuthMiddleware


def _app(username=None, password=None):
    app = FastAPI()
    app.add_middleware(BasicAuthMiddleware, username=username, password=password)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/secret")
    def secret():
        return {"ok": True}

    return app


def _basic(user, pw):
    token = base64.b64encode(f"{user}:{pw}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def test_noop_when_credentials_unset():
    client = TestClient(_app(username=None, password=None))
    assert client.get("/secret").status_code == 200


def test_blocks_without_credentials_when_enabled():
    client = TestClient(_app("admin", "pw"))
    r = client.get("/secret")
    assert r.status_code == 401
    assert r.headers["WWW-Authenticate"].startswith("Basic")


def test_allows_with_correct_credentials():
    client = TestClient(_app("admin", "pw"))
    assert client.get("/secret", headers=_basic("admin", "pw")).status_code == 200


def test_rejects_wrong_credentials():
    client = TestClient(_app("admin", "pw"))
    assert client.get("/secret", headers=_basic("admin", "nope")).status_code == 401


def test_health_exempt_even_when_enabled():
    client = TestClient(_app("admin", "pw"))
    assert client.get("/health").status_code == 200
