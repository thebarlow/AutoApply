"""Production access gate (pure ASGI).

In production, requests to /api/* require an authenticated session; all other
paths (SPA shell, /auth/*, /health, static assets) pass through so an
unauthenticated browser can load the app and render the login screen. Pure ASGI
(not BaseHTTPMiddleware) so the /api/events SSE stream is not buffered.

Requires SessionMiddleware to be registered OUTSIDE this one so scope["session"]
is populated before dispatch.
"""
from __future__ import annotations

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from core.env import is_production

_GATED_PREFIXES = ("/api/",)
_EXEMPT_PATHS = (
    "/api/payments/webhook",
    "/api/scraper/stage-job",
    "/api/ext/me",
)


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
        session = scope.get("session") or {}
        if session.get("account_id"):
            await self.app(scope, receive, send)
            return
        await JSONResponse({"detail": "Not authenticated"}, status_code=401)(scope, receive, send)
