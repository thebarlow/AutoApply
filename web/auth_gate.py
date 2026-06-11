"""HTTP Basic access gate for the single-user hosted instance.

Enabled only when both ``BASIC_AUTH_USER`` and ``BASIC_AUTH_PASSWORD`` are set;
otherwise every request passes through unchanged (local dev, tray app, browser
extension). ``GET /health`` is always exempt so platform healthchecks work
without credentials. This is an instance-wide gate, not per-tenant identity.
"""
from __future__ import annotations

import base64
import hmac
import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_EXEMPT_PATHS = {"/health"}


class BasicAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, username: str | None = None, password: str | None = None):
        super().__init__(app)
        self._user = username if username is not None else os.getenv("BASIC_AUTH_USER")
        self._pass = password if password is not None else os.getenv("BASIC_AUTH_PASSWORD")

    @property
    def _enabled(self) -> bool:
        return bool(self._user and self._pass)

    async def dispatch(self, request: Request, call_next):
        if not self._enabled or request.url.path in _EXEMPT_PATHS:
            return await call_next(request)
        if self._authorized(request.headers.get("Authorization", "")):
            return await call_next(request)
        return Response(
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="auto_apply"'},
        )

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
