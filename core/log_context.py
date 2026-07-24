"""Request-scoped logging context.

A ``contextvars``-backed bag of ``request_id``/``route``/``profile_id`` plus a
``logging.Filter`` that copies the current values onto every ``LogRecord`` so any
log line — request-scoped or background-thread — carries whatever context is
bound at emit time.
"""
from __future__ import annotations

import contextvars
import logging

_FIELDS = ("request_id", "route", "method", "profile_id", "account_email")

_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "log_request_id", default=None
)
_route: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "log_route", default=None
)
_method: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "log_method", default=None
)
_profile_id: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "log_profile_id", default=None
)
_account_email: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "log_account_email", default=None
)

_VARS = {
    "request_id": _request_id,
    "route": _route,
    "method": _method,
    "profile_id": _profile_id,
    "account_email": _account_email,
}


def bind(**fields: object) -> None:
    """Set any subset of ``request_id``/``route``/``method``/``profile_id``/``account_email`` on the context."""
    for name, value in fields.items():
        if name in _VARS:
            _VARS[name].set(value)  # type: ignore[arg-type]


def clear() -> None:
    """Reset every context field to ``None``."""
    for var in _VARS.values():
        var.set(None)


def snapshot() -> dict[str, object]:
    """Return the current context as a plain dict (missing values → ``None``)."""
    return {name: var.get() for name, var in _VARS.items()}


class ContextFilter(logging.Filter):
    """Inject the current context fields onto each ``LogRecord``."""

    def filter(self, record: logging.LogRecord) -> bool:
        for name, value in snapshot().items():
            setattr(record, name, value)
        return True
