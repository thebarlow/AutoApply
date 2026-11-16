"""Pure-ASGI cap on raw request-body size (audit H3).

Field-level caps (``core/limits.py``) only run after FastAPI has buffered and
parsed the whole body; multipart uploads are even spooled to disk first. This
middleware rejects an oversize body *before* the app reads it: an honest
``Content-Length`` over the cap gets an immediate 413, and a chunked/lying
client is cut off as soon as the bytes actually received cross the cap.
"""
from __future__ import annotations

import json

from core import limits as _lim

_UPLOAD_PATHS = frozenset({"/api/config/profile/upload"})


def _limit_for(path: str) -> int:
    if path in _UPLOAD_PATHS:
        return _lim.MAX_UPLOAD_BYTES + _lim.MULTIPART_OVERHEAD_BYTES
    return _lim.MAX_REQUEST_BODY_BYTES


async def _send_413(send, limit: int) -> None:
    body = json.dumps({
        "error": "payload_too_large",
        "detail": f"Request body too large (max {limit:,} bytes).",
    }).encode()
    await send({"type": "http.response.start", "status": 413,
                "headers": [(b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})


class BodySizeLimitMiddleware:
    """Reject HTTP requests whose body exceeds the per-path byte cap with 413."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = _limit_for(scope.get("path", ""))
        for name, value in scope.get("headers") or []:
            if name == b"content-length":
                try:
                    declared = int(value)
                except ValueError:
                    declared = 0
                if declared > limit:
                    await _send_413(send, limit)
                    return
                break

        received = 0
        started = False
        rejected = False

        async def capped_receive():
            # On overflow, answer 413 ourselves and hand the app a disconnect.
            # Raising instead would be swallowed by FastAPI's body parser and
            # turned into a generic 400.
            nonlocal received, rejected
            if rejected:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    rejected = True
                    if not started:
                        await _send_413(send, limit)
                    return {"type": "http.disconnect"}
            return message

        async def tracking_send(message):
            nonlocal started
            if rejected:
                return  # our 413 already went out; drop the app's error reply
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        await self.app(scope, capped_receive, tracking_send)
