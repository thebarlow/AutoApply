"""Pure-ASGI in-process rate limiter (audit H3).

Buckets (per-minute token buckets, env-tunable):

- ``auth``  — every ``/auth/*`` request (OAuth login/callback/logout), keyed by
  client IP. Default ``RATE_LIMIT_AUTH_PER_MIN=30``.
- ``api``   — unsafe methods (POST/PUT/PATCH/DELETE) under ``/api/``, keyed by
  account (session ``account_id`` → extension bearer-token hash → client IP).
  Default ``RATE_LIMIT_API_PER_MIN=120``.
- ``heavy`` — the subset of those that trigger an LLM call or a PDF render
  (``_HEAVY_ROUTES``), same key, counted *in addition* to ``api``.
  Default ``RATE_LIMIT_HEAVY_PER_MIN=20``.

Exempt: the Stripe webhook (Stripe retries from its own IPs and the handler is
signature-verified) and ``/health``. Safe methods under ``/api/`` (GET, the SSE
stream) are not limited. ``RATE_LIMIT_DISABLED=1`` turns the limiter off (the
test suite sets it).

A refusal is HTTP 429 ``{"error": "rate_limited"}`` with ``Retry-After``.

ASSUMPTION: a single app process. Railway runs one instance, so an in-memory
dict is authoritative. Scaling out to several replicas (or uvicorn workers)
multiplies every limit by the replica count — move the buckets to Redis/Postgres
before doing that.

Must run *inside* SessionMiddleware so ``scope["session"]`` is populated.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import threading
import time

from core.env import is_production

_UNSAFE = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_EXEMPT = frozenset({"/api/payments/webhook", "/health"})

# Routes that spend platform LLM tokens or render a PDF (verified against
# web/routers/{jobs,scraper,config,dev,llm_key}.py). Matched on unsafe methods.
_HEAVY_ROUTES = tuple(re.compile(p) for p in (
    r"^/api/jobs/[^/]+/score$",
    r"^/api/jobs/[^/]+/generate/(resume|cover)$",
    r"^/api/jobs/[^/]+/(resume|cover)/feedback$",
    r"^/api/jobs/[^/]+/(resume|cover)/document$",   # PUT: PDF re-render + ATS gate
    r"^/api/jobs/[^/]+/description/extract$",
    r"^/api/jobs/[^/]+/rematch-skills$",
    r"^/api/scraper/stage-job$",                    # spawns the intake pipeline
    r"^/api/scraper/scrape-selected$",              # up to 25 intake pipelines
    r"^/api/scraper/jobs/[^/]+/application-plan$",  # essay-draft LLM pass
    r"^/api/config/profiles/[^/]+/parse/propose$",
    r"^/api/config/section-prompt/draft$",
    r"^/api/profile/export-master$",                # PDF render
    r"^/api/dev/resume-compare/[^/]+$",
    r"^/api/account/llm-key/test$",                 # outbound call to a provider
))

_DEFAULTS = {"auth": 30, "api": 120, "heavy": 20}
_MAX_BUCKETS = 50_000  # memory guard: prune idle buckets past this many


def _per_min(bucket: str) -> int:
    raw = os.getenv(f"RATE_LIMIT_{bucket.upper()}_PER_MIN", "").strip()
    try:
        return max(1, int(raw)) if raw else _DEFAULTS[bucket]
    except ValueError:
        return _DEFAULTS[bucket]


def _disabled() -> bool:
    return os.getenv("RATE_LIMIT_DISABLED", "").strip().lower() in ("1", "true", "yes")


def is_heavy(path: str) -> bool:
    """True if ``path`` triggers an LLM call or PDF render."""
    return any(p.match(path) for p in _HEAVY_ROUTES)


class _Limiter:
    """Thread-safe per-key token buckets refilled continuously at ``limit``/minute."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buckets: dict[tuple[str, str], tuple[float, float]] = {}

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()

    def take(self, bucket: str, key: str, limit: int) -> float:
        """Consume one token; return 0 if allowed, else seconds until one frees up."""
        rate = limit / 60.0
        now = time.monotonic()
        with self._lock:
            tokens, last = self._buckets.get((bucket, key), (float(limit), now))
            tokens = min(float(limit), tokens + (now - last) * rate)
            if tokens >= 1.0:
                self._buckets[(bucket, key)] = (tokens - 1.0, now)
                if len(self._buckets) > _MAX_BUCKETS:
                    self._prune(now)
                return 0.0
            self._buckets[(bucket, key)] = (tokens, now)
            return (1.0 - tokens) / rate

    def _prune(self, now: float) -> None:
        # Buckets idle for over a minute have refilled completely; dropping them
        # is equivalent to keeping them.
        stale = [k for k, (_, last) in self._buckets.items() if now - last > 60.0]
        for k in stale:
            del self._buckets[k]


limiter = _Limiter()


def _header(scope, name: bytes) -> str:
    for k, v in scope.get("headers") or []:
        if k == name:
            return v.decode("latin-1")
    return ""


def client_ip(scope) -> str:
    """Client IP: first ``X-Forwarded-For`` hop behind Railway's proxy in
    production, else the socket peer."""
    if is_production():
        xff = _header(scope, b"x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
    client = scope.get("client")
    return client[0] if client else "unknown"


def _account_key(scope) -> str:
    session = scope.get("session") or {}
    account_id = session.get("account_id") if isinstance(session, dict) else None
    if account_id:
        return f"acct:{account_id}"
    auth = _header(scope, b"authorization")
    if auth[:7].lower() == "bearer " and auth[7:].strip():
        return "tok:" + hashlib.sha256(auth[7:].strip().encode()).hexdigest()[:32]
    return f"ip:{client_ip(scope)}"


async def _send_429(send, retry_after: float) -> None:
    secs = max(1, math.ceil(retry_after))
    body = json.dumps({"error": "rate_limited", "retry_after": secs}).encode()
    await send({"type": "http.response.start", "status": 429,
                "headers": [(b"content-type", b"application/json"),
                            (b"retry-after", str(secs).encode()),
                            (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})


class RateLimitMiddleware:
    """Refuse over-limit requests with 429 before they reach auth or the app."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or _disabled():
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if path in _EXEMPT:
            await self.app(scope, receive, send)
            return

        checks: list[tuple[str, str]] = []
        if path.startswith("/auth/"):
            checks.append(("auth", f"ip:{client_ip(scope)}"))
        elif path.startswith("/api/") and scope.get("method", "GET") in _UNSAFE:
            key = _account_key(scope)
            if is_heavy(path):
                checks.append(("heavy", key))
            checks.append(("api", key))

        for bucket, key in checks:
            wait = limiter.take(bucket, key, _per_min(bucket))
            if wait > 0:
                await _send_429(send, wait)
                return
        await self.app(scope, receive, send)
