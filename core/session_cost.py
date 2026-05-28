from __future__ import annotations

import threading
from datetime import datetime, timezone

_lock = threading.Lock()
_total: float = 0.0
_session_start: datetime = datetime.now(timezone.utc)


def add_cost(cost: float) -> None:
    global _total
    with _lock:
        _total += cost


def get_total() -> float:
    with _lock:
        return _total


def get_session_start() -> datetime:
    return _session_start


def reset() -> None:
    global _total
    with _lock:
        _total = 0.0
