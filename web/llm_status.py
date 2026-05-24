"""Thread-safe in-memory registry of job_keys currently in an LLM call.

Counts concurrent in-flight LLM operations per job_key. Broadcasts an SSE
envelope event only on 0->1 (start) and 1->0 (finish) transitions so the
frontend sees a single processing toggle per job.
"""
from __future__ import annotations

import threading


_lock = threading.Lock()
_counts: dict[str, int] = {}


def start(job_key: str) -> None:
    """Mark job_key as having an in-flight LLM op. Broadcasts on 0->1 transition."""
    with _lock:
        new = _counts.get(job_key, 0) + 1
        _counts[job_key] = new
        emit = new == 1
    if emit:
        _send(job_key, True)


def finish(job_key: str) -> None:
    """Decrement. Broadcasts on 1->0 transition."""
    with _lock:
        cur = _counts.get(job_key, 0)
        if cur <= 1:
            _counts.pop(job_key, None)
            emit = cur == 1  # only broadcast if we were actually tracking
        else:
            _counts[job_key] = cur - 1
            emit = False
    if emit:
        _send(job_key, False)


def is_processing(job_key: str) -> bool:
    """Return True if an LLM op is currently in flight for job_key."""
    with _lock:
        return _counts.get(job_key, 0) > 0


def snapshot() -> list[str]:
    """Return job_keys currently in-flight."""
    with _lock:
        return [k for k, v in _counts.items() if v > 0]


def _send(job_key: str, processing: bool) -> None:
    from web.sse import send
    send("llm_status", {"job_key": job_key, "processing": processing})
