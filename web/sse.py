"""Thread-safe SSE broadcaster.

Sync route handlers call broadcast() to push a JSON payload to all connected
clients. Each SSE client holds its own SimpleQueue. broadcast() posts to every
queue synchronously — safe to call from FastAPI's threadpool workers.
"""
from __future__ import annotations

import queue
from typing import List


_clients: List[queue.SimpleQueue] = []


def subscribe() -> queue.SimpleQueue:
    """Register a new SSE client and return its queue."""
    q: queue.SimpleQueue = queue.SimpleQueue()
    _clients.append(q)
    return q


def unsubscribe(q: queue.SimpleQueue) -> None:
    """Remove a client queue when its connection closes."""
    try:
        _clients.remove(q)
    except ValueError:
        pass


def broadcast(payload: str) -> None:
    """Send a JSON string to every connected SSE client."""
    for q in list(_clients):
        try:
            q.put_nowait(payload)
        except Exception:
            pass
