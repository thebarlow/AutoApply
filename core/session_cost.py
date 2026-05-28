from __future__ import annotations

import threading

_lock = threading.Lock()
_total: float = 0.0


def add_cost(cost: float) -> None:
    global _total
    with _lock:
        _total += cost


def get_total() -> float:
    with _lock:
        return _total


def reset() -> None:
    global _total
    with _lock:
        _total = 0.0
