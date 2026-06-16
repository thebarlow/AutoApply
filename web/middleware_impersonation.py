"""Read-only guard for impersonation sessions (pure ASGI).

While an admin is impersonating a user (session carries impersonate_profile_id),
all unsafe HTTP methods are rejected so the admin can only VIEW the user's data,
never mutate it or spend their credits. A small allowlist lets the admin exit
impersonation and log out.

Pure ASGI (not BaseHTTPMiddleware) so the /api/events SSE stream is not buffered.
Requires SessionMiddleware to be registered OUTSIDE this one so scope["session"]
is populated before dispatch.
"""
from __future__ import annotations

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_ALLOWLIST = {"/api/admin/impersonate/stop", "/auth/logout"}


def is_blocked(method: str, path: str, session: dict) -> bool:
    """True if this request must be rejected because an impersonation is active."""
    if not session.get("impersonate_profile_id"):
        return False
    if method.upper() not in _UNSAFE_METHODS:
        return False
    return path not in _ALLOWLIST


class ImpersonationReadOnlyMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        session = scope.get("session") or {}
        if is_blocked(scope.get("method", "GET"), scope.get("path", ""), session):
            await JSONResponse(
                {"error": "impersonation_read_only"}, status_code=403,
            )(scope, receive, send)
            return
        await self.app(scope, receive, send)
