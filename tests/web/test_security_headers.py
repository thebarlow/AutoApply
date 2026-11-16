"""Security headers (audit M3) and production API-docs lockdown (audit L2)."""
import pytest
from fastapi import FastAPI
from fastapi.responses import Response
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from web.auth.middleware import AuthGateMiddleware
from web.middleware_security_headers import (
    CONTENT_SECURITY_POLICY,
    HSTS,
    SecurityHeadersMiddleware,
)


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(AuthGateMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(SessionMiddleware, secret_key="test")

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/api/secret")
    def secret():
        return {"ok": True}

    @app.get("/doc.pdf")
    def pdf():
        return Response(b"%PDF-1.4", media_type="application/pdf")

    @app.get("/custom")
    def custom():
        return Response("x", headers={"X-Frame-Options": "SAMEORIGIN"})

    return app


def _assert_baseline(r):
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_headers_present_in_dev(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    r = TestClient(_app()).get("/health")
    _assert_baseline(r)
    assert r.headers["X-Frame-Options"] == "DENY"
    csp = r.headers["Content-Security-Policy"]
    assert csp == CONTENT_SECURITY_POLICY
    assert "frame-ancestors 'none'" in csp and "object-src 'none'" in csp
    assert "Strict-Transport-Security" not in r.headers


def test_hsts_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    r = TestClient(_app()).get("/health")
    _assert_baseline(r)
    assert r.headers["Strict-Transport-Security"] == HSTS


def test_gate_401_also_carries_headers(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    r = TestClient(_app()).get("/api/secret")
    assert r.status_code == 401
    _assert_baseline(r)
    assert "Content-Security-Policy" in r.headers


def test_pdf_is_frameable_same_origin_only(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    r = TestClient(_app()).get("/doc.pdf")
    assert r.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert r.headers["Content-Security-Policy"] == "frame-ancestors 'self'"
    _assert_baseline(r)


def test_route_set_header_not_overridden(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    r = TestClient(_app()).get("/custom")
    assert r.headers["X-Frame-Options"] == "SAMEORIGIN"


def test_real_app_sets_headers():
    from web.main import app

    r = TestClient(app).get("/health")
    _assert_baseline(r)
    assert r.headers["Content-Security-Policy"] == CONTENT_SECURITY_POLICY


def test_api_docs_disabled_in_production(monkeypatch):
    from web.main import _api_docs_kwargs

    monkeypatch.setenv("APP_ENV", "production")
    kwargs = _api_docs_kwargs()
    assert kwargs == {"docs_url": None, "redoc_url": None, "openapi_url": None}
    client = TestClient(FastAPI(**kwargs))
    for path in ("/endpoints", "/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404


def test_api_docs_enabled_in_dev(monkeypatch):
    from web.main import _api_docs_kwargs

    monkeypatch.delenv("APP_ENV", raising=False)
    client = TestClient(FastAPI(**_api_docs_kwargs()))
    assert client.get("/endpoints").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_dev_swagger_ui_skips_csp(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    from web.main import app

    r = TestClient(app).get("/endpoints")
    assert r.status_code == 200
    assert "Content-Security-Policy" not in r.headers
    _assert_baseline(r)
