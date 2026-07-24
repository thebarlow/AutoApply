"""Persist ERROR-level log records to the ``error_events`` table.

A ``logging.Handler`` that writes in its own short-lived session, dedups by a
stable fingerprint, prunes to configured bounds, and swallows every exception so
logging can never cascade-fail.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import threading
from datetime import datetime, timedelta, timezone

_ADDR_RE = re.compile(r"0x[0-9a-fA-F]+")
_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
_QUOTED_RE = re.compile(r"'[^']*'|\"[^\"]*\"")
# Strip 1-2 digit and 4+ digit runs (ids, counts) but PRESERVE standalone
# 3-digit numbers so HTTP status / error codes (404, 500) stay distinct.
_INT_RE = re.compile(r"\b\d{1,2}\b|\b\d{4,}\b")


def _normalize(text: str) -> str:
    """Strip volatile tokens (addresses, UUIDs, quoted literals, integers).

    Applied only to fingerprint inputs so the same underlying error dedups
    even when its message embeds request-specific ids or values. The full
    original message is still stored verbatim in the ``message`` column.
    Standalone 3-digit numbers (e.g. HTTP status/error codes like 404, 500)
    are preserved rather than stripped, so errors differing only by code
    remain distinct fingerprints.
    """
    text = _ADDR_RE.sub("0xADDR", text)
    text = _UUID_RE.sub("<uuid>", text)
    text = _QUOTED_RE.sub("<str>", text)
    text = _INT_RE.sub("<n>", text)
    return text


def _now() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def fingerprint(record: logging.LogRecord) -> str:
    """Return a stable dedup key: logger + exception type + normalized top frame.

    Falls back to ``logger + message`` when there is no ``exc_info``. Memory
    addresses are normalized so the same underlying error dedups across
    releases/process restarts (addresses differ; the frame doesn't).
    """
    parts = [record.name]
    if record.exc_info and record.exc_info[0] is not None:
        parts.append(record.exc_info[0].__name__)
        # Top-of-stack file:function, line numbers/addresses stripped.
        import traceback

        tb = record.exc_info[2]
        frames = traceback.extract_tb(tb)
        if frames:
            top = frames[-1]
            parts.append(f"{top.filename}:{top.name}")
        parts.append(str(record.exc_info[1]))
    else:
        parts.append(record.getMessage())
    raw = "|".join(_normalize(p) for p in parts)
    return hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()


def _max_rows() -> int:
    """Return ``ERROR_LOG_MAX_ROWS`` (default 1000), tolerating bad env values."""
    try:
        return int(os.environ.get("ERROR_LOG_MAX_ROWS", "1000"))
    except ValueError:
        return 1000


def _max_age_days() -> int:
    """Return ``ERROR_LOG_MAX_AGE_DAYS`` (default 30), tolerating bad env values."""
    try:
        return int(os.environ.get("ERROR_LOG_MAX_AGE_DAYS", "30"))
    except ValueError:
        return 30


class DbErrorHandler(logging.Handler):
    """Write ERROR records to ``error_events`` (dedup + prune). Never raises."""

    _local = threading.local()

    def emit(self, record: logging.LogRecord) -> None:
        """Persist ``record``, swallowing all exceptions (logging must not fail).

        Guarded against re-entrancy: if this handler's own DB work ever emits
        an ERROR log, the guard prevents an infinite recursive emit loop.
        """
        if getattr(self._local, "in_emit", False):
            return
        self._local.in_emit = True
        try:
            self._emit(record)
        except Exception:  # logging must never cascade-fail
            pass
        finally:
            self._local.in_emit = False

    def _emit(self, record: logging.LogRecord) -> None:
        """Upsert-by-fingerprint then prune, using a fresh, short-lived session."""
        from db.database import ErrorEvent, SessionLocal

        fp = fingerprint(record)
        now = _now()
        tb = self.format_traceback(record)
        db = SessionLocal()
        try:
            existing = (
                db.query(ErrorEvent)
                .filter(ErrorEvent.fingerprint == fp)
                .order_by(ErrorEvent.id.desc())
                .first()
            )
            if existing is not None:
                existing.count += 1
                existing.last_seen = now
                existing.traceback = tb
                existing.message = record.getMessage()
                existing.route = getattr(record, "route", None)
                existing.profile_id = getattr(record, "profile_id", None)
                existing.request_id = getattr(record, "request_id", None)
                existing.method = getattr(record, "method", None)
                existing.account_email = getattr(record, "account_email", None)
                db.commit()
            else:
                db.add(
                    ErrorEvent(
                        created_at=now,
                        last_seen=now,
                        count=1,
                        level=record.levelname,
                        logger=record.name,
                        message=record.getMessage(),
                        traceback=tb,
                        route=getattr(record, "route", None),
                        profile_id=getattr(record, "profile_id", None),
                        request_id=getattr(record, "request_id", None),
                        method=getattr(record, "method", None),
                        account_email=getattr(record, "account_email", None),
                        fingerprint=fp,
                    )
                )
                db.commit()
                self._prune(db)
        finally:
            db.close()

    def format_traceback(self, record: logging.LogRecord) -> str | None:
        """Return the formatted traceback for ``record``, or ``None`` if absent."""
        if not record.exc_info:
            return None
        import traceback

        return "".join(traceback.format_exception(*record.exc_info))

    def _prune(self, db) -> None:
        """Delete rows older than ``ERROR_LOG_MAX_AGE_DAYS`` and cap total rows."""
        from db.database import ErrorEvent

        cutoff = (datetime.now(timezone.utc) - timedelta(days=_max_age_days())).isoformat()
        db.query(ErrorEvent).filter(ErrorEvent.last_seen < cutoff).delete(
            synchronize_session=False
        )
        max_rows = _max_rows()
        surplus = db.query(ErrorEvent).count() - max_rows
        if surplus > 0:
            old_ids = [
                r.id
                for r in db.query(ErrorEvent.id)
                .order_by(ErrorEvent.last_seen.asc())
                .limit(surplus)
                .all()
            ]
            db.query(ErrorEvent).filter(ErrorEvent.id.in_(old_ids)).delete(
                synchronize_session=False
            )
        db.commit()


def install_db_error_handler(root: logging.Logger) -> None:
    """Attach a ``DbErrorHandler`` at ERROR level unless ``ERROR_LOG_DB`` disables it."""
    if os.environ.get("ERROR_LOG_DB", "1").lower() in ("0", "false", "no"):
        return
    handler = DbErrorHandler()
    handler.setLevel(logging.ERROR)
    root.addHandler(handler)
