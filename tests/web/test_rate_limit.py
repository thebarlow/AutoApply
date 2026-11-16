"""In-process rate limiter (audit H3)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.responses import PlainTextResponse

from web import middleware_rate_limit as rl


async def _ok(scope, receive, send):
    await PlainTextResponse("ok")(scope, receive, send)


class _FakeSession:
    """Stand-in for SessionMiddleware: account id comes from a test header."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            acct = dict(scope["headers"]).get(b"x-test-account")
            scope["session"] = {"account_id": int(acct)} if acct else {}
        await self.app(scope, receive, send)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("RATE_LIMIT_DISABLED", raising=False)
    monkeypatch.setenv("RATE_LIMIT_API_PER_MIN", "5")
    monkeypatch.setenv("RATE_LIMIT_HEAVY_PER_MIN", "2")
    monkeypatch.setenv("RATE_LIMIT_AUTH_PER_MIN", "3")
    rl.limiter.reset()
    yield TestClient(_FakeSession(rl.RateLimitMiddleware(_ok)))
    rl.limiter.reset()


def _burst(client, n, method="post", path="/api/jobs/k/flag", **kw):
    return [getattr(client, method)(path, **kw).status_code for _ in range(n)]


def test_burst_over_api_limit_gets_429_with_retry_after(client):
    codes = _burst(client, 5, headers={"x-test-account": "1"})
    assert codes == [200] * 5
    r = client.post("/api/jobs/k/flag", headers={"x-test-account": "1"})
    assert r.status_code == 429
    assert r.json()["error"] == "rate_limited"
    assert int(r.headers["retry-after"]) >= 1


def test_heavy_route_has_stricter_bucket(client):
    codes = _burst(client, 3, path="/api/jobs/k/generate/resume",
                   headers={"x-test-account": "1"})
    assert codes == [200, 200, 429]
    # The general bucket still has room for non-heavy writes.
    assert client.post("/api/jobs/k/flag", headers={"x-test-account": "1"}).status_code == 200


def test_accounts_are_isolated(client):
    assert 429 in _burst(client, 6, headers={"x-test-account": "1"})
    assert client.post("/api/jobs/k/flag", headers={"x-test-account": "2"}).status_code == 200


def test_bearer_token_keyed_separately_from_ip(client):
    assert 429 in _burst(client, 6, headers={"authorization": "Bearer tok-a"})
    assert client.post("/api/jobs/k/flag",
                       headers={"authorization": "Bearer tok-b"}).status_code == 200


def test_stripe_webhook_and_health_exempt(client):
    assert set(_burst(client, 10, path="/api/payments/webhook")) == {200}
    assert set(_burst(client, 10, method="get", path="/health")) == {200}


def test_safe_methods_not_limited(client):
    assert set(_burst(client, 10, method="get", path="/api/jobs",
                      headers={"x-test-account": "1"})) == {200}


def test_auth_routes_limited_per_ip(client):
    codes = _burst(client, 4, method="get", path="/auth/login/google")
    assert codes == [200, 200, 200, 429]


def test_disabled_by_env(client, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_DISABLED", "1")
    assert set(_burst(client, 10, headers={"x-test-account": "1"})) == {200}


def test_client_ip_uses_first_xff_hop_only_in_production(monkeypatch):
    scope = {"headers": [(b"x-forwarded-for", b"1.2.3.4, 10.0.0.1")],
             "client": ("10.0.0.9", 1234)}
    monkeypatch.setattr(rl, "is_production", lambda: False)
    assert rl.client_ip(scope) == "10.0.0.9"
    monkeypatch.setattr(rl, "is_production", lambda: True)
    assert rl.client_ip(scope) == "1.2.3.4"


def test_registered_on_real_app_and_webhook_exempt(monkeypatch):
    """Through the real middleware stack: the webhook is never 429'd."""
    from web.main import app
    monkeypatch.delenv("RATE_LIMIT_DISABLED", raising=False)
    monkeypatch.setenv("RATE_LIMIT_API_PER_MIN", "1")
    rl.limiter.reset()
    try:
        c = TestClient(app)
        codes = [c.post("/api/payments/webhook", content=b"{}").status_code
                 for _ in range(3)]
        assert 429 not in codes
        codes = [c.post("/api/jobs/k/flag", json={"flagged": True}).status_code
                 for _ in range(3)]
        assert codes[-1] == 429
    finally:
        rl.limiter.reset()


def test_heavy_patterns_match_real_routes():
    for path in ("/api/jobs/abc/score", "/api/jobs/abc/generate/cover",
                 "/api/jobs/abc/cover/feedback", "/api/jobs/abc/resume/document",
                 "/api/jobs/abc/description/extract", "/api/jobs/abc/rematch-skills",
                 "/api/scraper/stage-job", "/api/scraper/scrape-selected",
                 "/api/scraper/jobs/abc/application-plan",
                 "/api/config/profiles/1/parse/propose",
                 "/api/config/section-prompt/draft", "/api/profile/export-master",
                 "/api/account/llm-key/test"):
        assert rl.is_heavy(path), path
    assert not rl.is_heavy("/api/jobs/abc/flag")
