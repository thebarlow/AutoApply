"""Thread-safe in-memory registry of in-flight LLM ops per tenant + job + action.

Tracks two layers, both keyed by ``(profile_id, job_key)`` so tenants who happen
to share a ``job_key`` (unique only per profile) never collide:
- per-job counts: drive the job-level processing toggle (one event per 0<->1
  transition across all actions for a given job_key).
- per-(job, action) counts: drive per-action events so the UI can light up
  individual subtabs (description, resume, cover, score).

Both transitions are broadcast via SSE, scoped to the owning tenant.
"""
from __future__ import annotations

import threading


_lock = threading.Lock()
_counts: dict[tuple[int, str], int] = {}
_action_counts: dict[tuple[int, str, str], int] = {}


def start(profile_id: int, job_key: str, action: str | None = None) -> None:
    """Mark an in-flight LLM op for a tenant's job_key (optionally action-scoped).

    Broadcasts:
    - `llm_status` on the job's 0->1 transition.
    - `llm_action` on the (job, action) 0->1 transition (if action given).
    """
    with _lock:
        jkey = (profile_id, job_key)
        new_job = _counts.get(jkey, 0) + 1
        _counts[jkey] = new_job
        emit_job = new_job == 1

        emit_action = False
        if action is not None:
            key = (profile_id, job_key, action)
            new_action = _action_counts.get(key, 0) + 1
            _action_counts[key] = new_action
            emit_action = new_action == 1

    if emit_job:
        _send_status(profile_id, job_key, True)
    if emit_action:
        _send_action(profile_id, job_key, action, True)


def finish(profile_id: int, job_key: str, action: str | None = None) -> None:
    """Decrement counters. Broadcasts on 1->0 transitions."""
    with _lock:
        jkey = (profile_id, job_key)
        cur_job = _counts.get(jkey, 0)
        if cur_job <= 1:
            _counts.pop(jkey, None)
            emit_job = cur_job == 1
        else:
            _counts[jkey] = cur_job - 1
            emit_job = False

        emit_action = False
        if action is not None:
            key = (profile_id, job_key, action)
            cur_action = _action_counts.get(key, 0)
            if cur_action <= 1:
                _action_counts.pop(key, None)
                emit_action = cur_action == 1
            else:
                _action_counts[key] = cur_action - 1
                emit_action = False

    if emit_job:
        _send_status(profile_id, job_key, False)
    if emit_action:
        _send_action(profile_id, job_key, action, False)


def snapshot(profile_id: int) -> list[str]:
    """Return the tenant's job_keys with any in-flight op."""
    with _lock:
        return [jk for (pid, jk), v in _counts.items() if pid == profile_id and v > 0]


def action_snapshot(profile_id: int) -> dict[str, list[str]]:
    """Return {job_key: [action, ...]} for the tenant's in-flight (job, action) pairs."""
    out: dict[str, list[str]] = {}
    with _lock:
        for (pid, jk, action), v in _action_counts.items():
            if pid == profile_id and v > 0:
                out.setdefault(jk, []).append(action)
    return out


def _send_status(profile_id: int, job_key: str, processing: bool) -> None:
    from web.sse import send
    send("llm_status", {"job_key": job_key, "processing": processing}, profile_id=profile_id)


def _send_action(profile_id: int, job_key: str, action: str, processing: bool) -> None:
    from web.sse import send
    send("llm_action", {"job_key": job_key, "action": action, "processing": processing},
         profile_id=profile_id)
