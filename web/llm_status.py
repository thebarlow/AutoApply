"""Thread-safe in-memory registry of in-flight LLM ops per job + action.

Tracks two layers:
- per-job counts: drive the job-level processing toggle (one event per 0<->1
  transition across all actions for a given job_key).
- per-(job, action) counts: drive per-action events so the UI can light up
  individual subtabs (description, resume, cover, score).

Both transitions are broadcast via SSE.
"""
from __future__ import annotations

import threading


_lock = threading.Lock()
_counts: dict[str, int] = {}
_action_counts: dict[tuple[str, str], int] = {}


def start(job_key: str, action: str | None = None) -> None:
    """Mark an in-flight LLM op for job_key (optionally action-scoped).

    Broadcasts:
    - `llm_status` on the job's 0->1 transition.
    - `llm_action` on the (job, action) 0->1 transition (if action given).
    """
    with _lock:
        new_job = _counts.get(job_key, 0) + 1
        _counts[job_key] = new_job
        emit_job = new_job == 1

        emit_action = False
        if action is not None:
            key = (job_key, action)
            new_action = _action_counts.get(key, 0) + 1
            _action_counts[key] = new_action
            emit_action = new_action == 1

    if emit_job:
        _send_status(job_key, True)
    if emit_action:
        _send_action(job_key, action, True)


def finish(job_key: str, action: str | None = None) -> None:
    """Decrement counters. Broadcasts on 1->0 transitions."""
    with _lock:
        cur_job = _counts.get(job_key, 0)
        if cur_job <= 1:
            _counts.pop(job_key, None)
            emit_job = cur_job == 1
        else:
            _counts[job_key] = cur_job - 1
            emit_job = False

        emit_action = False
        if action is not None:
            key = (job_key, action)
            cur_action = _action_counts.get(key, 0)
            if cur_action <= 1:
                _action_counts.pop(key, None)
                emit_action = cur_action == 1
            else:
                _action_counts[key] = cur_action - 1
                emit_action = False

    if emit_job:
        _send_status(job_key, False)
    if emit_action:
        _send_action(job_key, action, False)


def is_processing(job_key: str) -> bool:
    """Return True if any LLM op is in flight for job_key."""
    with _lock:
        return _counts.get(job_key, 0) > 0


def snapshot() -> list[str]:
    """Return job_keys with any in-flight op."""
    with _lock:
        return [k for k, v in _counts.items() if v > 0]


def action_snapshot() -> dict[str, list[str]]:
    """Return {job_key: [action, ...]} for all in-flight (job, action) pairs."""
    out: dict[str, list[str]] = {}
    with _lock:
        for (jk, action), v in _action_counts.items():
            if v > 0:
                out.setdefault(jk, []).append(action)
    return out


def _send_status(job_key: str, processing: bool) -> None:
    from web.sse import send
    send("llm_status", {"job_key": job_key, "processing": processing})


def _send_action(job_key: str, action: str, processing: bool) -> None:
    from web.sse import send
    send("llm_action", {"job_key": job_key, "action": action, "processing": processing})
