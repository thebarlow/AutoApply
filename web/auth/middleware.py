"""Production access gate (pure ASGI).

In production, requests to /api/* require an authenticated session; all other
paths (SPA shell, /auth/*, /health, static assets) pass through so an
unauthenticated browser can load the app and render the login screen. Pure ASGI
(not BaseHTTPMiddleware) so the /api/events SSE stream is not buffered.

Requires SessionMiddleware to be registered OUTSIDE this one so scope["session"]
is populated before dispatch.
"""
from __future__ import annotations

import logging

from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from core.env import is_production

_GATED_PREFIXES = ("/api/",)
_EXEMPT_PATHS = (
    "/api/payments/webhook",
    "/api/scraper/stage-job",
    "/api/ext/me",
)

logger = logging.getLogger(__name__)

OK, BANNED, MISSING = "ok", "banned", "missing"


def _account_state(account_id) -> str:
    """Return OK / BANNED / MISSING for a session's account (one indexed lookup).

    Uses the module-level SessionLocal (same pattern as
    web/middleware_request_context._resolve_identity). Raises on DB failure so
    the caller can fail closed without logging the user out.
    """
    from db.database import Account, SessionLocal

    db = SessionLocal()
    try:
        row = db.query(Account.banned).filter(Account.id == account_id).first()
    finally:
        db.close()
    if row is None:
        return MISSING
    return BANNED if row[0] else OK


class AuthGateMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not is_production():
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if not path.startswith(_GATED_PREFIXES) or path in _EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return
        session = scope.get("session")
        account_id = session.get("account_id") if session else None
        if not account_id:
            await _reject(scope, receive, send, "Not authenticated")
            return
        # Re-check the account on every request: a ban (or account deletion)
        # must end an already-issued session immediately, not at cookie expiry.
        try:
            state = await run_in_threadpool(_account_state, account_id)
        except Exception:
            logger.exception("auth gate account lookup failed")
            await JSONResponse(
                {"detail": "Service unavailable"}, status_code=503
            )(scope, receive, send)
            return
        if state != OK:
            session.clear()  # SessionMiddleware then expires the cookie
            detail = "account suspended" if state == BANNED else "Not authenticated"
            await _reject(scope, receive, send, detail)
            return
        await self.app(scope, receive, send)


async def _reject(scope: Scope, receive: Receive, send: Send, detail: str) -> None:
    await JSONResponse({"detail": detail}, status_code=401)(scope, receive, send)
