"""SSE streaming endpoint — `GET /api/events`.

Clients receive a `data: <json>\n\n` event whenever a job is written to the DB.
The event payload is the full serialized job object.
"""
from __future__ import annotations

import asyncio
import os
import queue as _queue

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse

from web.sse import subscribe, unsubscribe
from web.tenancy import current_profile_id

router = APIRouter(prefix="/api")

# Each open stream is a polling coroutine; cap them per tenant (1 account = 1
# profile) so one user can't pin the event loop with hundreds of tabs (audit M1).
_DEFAULT_MAX_STREAMS = 5
# Queue poll interval. Events are UI nudges (job updates, spinners), so ~250ms
# latency is invisible while costing 5x fewer wakeups than the old 50ms loop.
POLL_INTERVAL_S = 0.25


def _max_streams() -> int:
    try:
        return max(1, int(os.getenv("SSE_MAX_STREAMS_PER_ACCOUNT", "") or _DEFAULT_MAX_STREAMS))
    except ValueError:
        return _DEFAULT_MAX_STREAMS


@router.get("/events")
async def sse_events(profile_id: int = Depends(current_profile_id)):
    # Scope the stream to the caller's tenant so job events (which carry full,
    # tenant-private payloads) never fan out to other tenants' clients.
    q = subscribe(profile_id, max_per_profile=_max_streams())
    if q is None:
        return JSONResponse(
            status_code=429,
            content={"error": "rate_limited", "detail": "Too many open event streams."},
            headers={"Retry-After": "30"},
        )

    async def generate():
        try:
            while True:
                try:
                    payload = q.get_nowait()
                    yield f"data: {payload}\n\n"
                except _queue.Empty:
                    await asyncio.sleep(POLL_INTERVAL_S)
        finally:
            unsubscribe(q)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
