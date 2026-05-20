"""SSE streaming endpoint — `GET /api/events`.

Clients receive a `data: <json>\n\n` event whenever a job is written to the DB.
The event payload is the full serialized job object.
"""
from __future__ import annotations

import asyncio
import queue as _queue

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from web.sse import subscribe, unsubscribe

router = APIRouter(prefix="/api")


@router.get("/events")
async def sse_events() -> StreamingResponse:
    q = subscribe()

    async def generate():
        try:
            while True:
                try:
                    payload = q.get_nowait()
                    yield f"data: {payload}\n\n"
                except _queue.Empty:
                    await asyncio.sleep(0.05)
        finally:
            unsubscribe(q)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
