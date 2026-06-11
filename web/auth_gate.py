"""HTTP Basic access gate for the single-user hosted instance.

Enabled only when both ``BASIC_AUTH_USER`` and ``BASIC_AUTH_PASSWORD`` are set;
otherwise every request passes through unchanged (local dev, tray app, browser
extension). ``GET /health`` is always exempt so platform healthchecks work
without credentials. This is an instance-wide gate, not per-tenant identity.

Implemented as raw ASGI middleware (not BaseHTTPMiddleware) so it does not
buffer response bodies — long-lived ``StreamingResponse`` / SSE endpoints
(e.g. ``GET /events``) stream through unbuffered.
"""
from __future__ import annotations

import base64
import hmac
import os

from starlette.datastructures import Headers
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

_EXEMPT_PATHS = {"/health"}


class BasicAuthMiddleware:
    def __init__(self, app: ASGIApp, username: str | None = None, password: str | None = None):
        self.app = app
        self._user = username if username is not None else os.getenv("BASIC_AUTH_USER")
        self._pass = password if password is not None else os.getenv("BASIC_AUTH_PASSWORD")

    @property
    def _enabled(self) -> bool:
        return bool(self._user and self._pass)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self._enabled or scope["path"] in _EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        if self._authorized(headers.get("Authorization", "")):
            await self.app(scope, receive, send)
            return
        response = Response(
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="auto_apply"'},
        )
        await response(scope, receive, send)

    def _authorized(self, header: str) -> bool:
        if not header.startswith("Basic "):
            return False
        try:
            decoded = base64.b64decode(header[len("Basic "):]).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return False
        user, _, pw = decoded.partition(":")
        # constant-time comparison to avoid leaking credential length/content
        return hmac.compare_digest(user, self._user or "") and hmac.compare_digest(
            pw, self._pass or ""
        )
