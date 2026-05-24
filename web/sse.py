"""Thread-safe SSE broadcaster.

Sync route handlers call broadcast() to push a JSON payload to all connected
clients. Each SSE client holds its own SimpleQueue. broadcast() posts to every
queue synchronously — safe to call from FastAPI's threadpool workers.
"""
from __future__ import annotations

import queue
import threading


_lock = threading.Lock()
_clients: list[queue.SimpleQueue] = []


def subscribe() -> queue.SimpleQueue:
    """Register a new SSE client and return its queue."""
    q: queue.SimpleQueue = queue.SimpleQueue()
    with _lock:
        _clients.append(q)
    return q


def unsubscribe(q: queue.SimpleQueue) -> None:
    """Remove a client queue when its connection closes."""
    with _lock:
        try:
            _clients.remove(q)
        except ValueError:
            pass


def broadcast(payload: str) -> None:
    """Send a JSON string to every connected SSE client."""
    with _lock:
        clients = list(_clients)
    for q in clients:
        q.put_nowait(payload)


def send(type_: str, data: dict) -> None:
    """Broadcast an envelope-shaped SSE event."""
    import json
    broadcast(json.dumps({"type": type_, "data": data}))
