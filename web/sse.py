"""Thread-safe, tenant-scoped SSE broadcaster.

Sync route handlers call ``send()`` to push a JSON payload to connected clients.
Each SSE client subscribes with its owning ``profile_id`` and holds its own
SimpleQueue. A ``send`` targeted at a ``profile_id`` reaches only that tenant's
clients; a ``send`` with ``profile_id=None`` is a genuinely global event (e.g.
platform LLM up/down) and reaches everyone. This prevents one tenant's job data
from leaking onto another tenant's live stream. Safe to call from FastAPI's
threadpool workers.
"""
from __future__ import annotations

import json
import queue
import threading


_lock = threading.Lock()
# (queue, owning profile_id or None for an unscoped/local subscriber)
_clients: list[tuple[queue.SimpleQueue, int | None]] = []


def subscribe(profile_id: int | None = None) -> queue.SimpleQueue:
    """Register a new SSE client for a tenant and return its queue."""
    q: queue.SimpleQueue = queue.SimpleQueue()
    with _lock:
        _clients.append((q, profile_id))
    return q


def unsubscribe(q: queue.SimpleQueue) -> None:
    """Remove a client queue when its connection closes."""
    with _lock:
        _clients[:] = [(cq, pid) for (cq, pid) in _clients if cq is not q]


def broadcast(payload: str, *, profile_id: int | None = None) -> None:
    """Send a JSON string to connected clients.

    ``profile_id=None`` fans out to every client (a global event). Otherwise the
    payload reaches only clients that subscribed for that ``profile_id``.
    """
    with _lock:
        targets = [q for (q, pid) in _clients if profile_id is None or pid == profile_id]
    for q in targets:
        q.put_nowait(payload)


def send(type_: str, data: dict, *, profile_id: int | None = None) -> None:
    """Broadcast an envelope-shaped SSE event, optionally scoped to one tenant."""
    broadcast(json.dumps({"type": type_, "data": data}), profile_id=profile_id)
