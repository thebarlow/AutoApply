"""Bind per-request logging context (request id, route, profile) for every request."""
from __future__ import annotations

import logging
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from core import log_context

logger = logging.getLogger("web.request")


def _resolve_profile_id(request: Request) -> int | None:
    """Best-effort profile id from the session; never raises."""
    try:
        account_id = request.session.get("account_id")
    except Exception:
        return None  # SessionMiddleware not installed / no session
    if not account_id:
        return None
    try:
        from db.database import Account, SessionLocal

        db = SessionLocal()
        try:
            acct = db.query(Account).filter_by(id=account_id).first()
            return acct.profile_id if acct else None
        finally:
            db.close()
    except Exception:
        return None


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Populate ``core.log_context`` for the duration of each request."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = uuid.uuid4().hex
        # NOTE: `route` is the raw request path (e.g. "/jobs/123"), not the matched
        # route template ("/jobs/{job_id}") — BaseHTTPMiddleware binds context before
        # routing resolves the template inside call_next. Parameterized routes thus
        # produce higher-cardinality route values in error_events/logs.
        route = request.scope.get("path", "")
        log_context.bind(
            request_id=request_id,
            route=route,
            profile_id=_resolve_profile_id(request),
        )
        try:
            response = await call_next(request)
        except Exception:
            # Log here — the context bag is still bound, so the record (and its
            # error_events row) carries request_id/route/profile_id. The app-level
            # Exception handler runs in ServerErrorMiddleware, OUTSIDE this
            # middleware, after clear() below has wiped the context.
            logger.exception("Unhandled exception on %s", route)
            raise
        finally:
            log_context.clear()
        response.headers["X-Request-ID"] = request_id
        return response
