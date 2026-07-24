# Hosted Error Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make production failures on Railway durable and diagnosable via JSON logs, a self-pruning DB error table, and an in-app admin viewer.

**Architecture:** A JSON console formatter (prod) + a contextvar-backed logging filter enrich every log line with `request_id`/`route`/`profile_id`. A root-attached `ERROR`-level handler persists errors to a new `error_events` table (own session, deduped by fingerprint, prune-on-insert). Admin API + React panel surface them.

**Tech Stack:** Python 3, FastAPI, SQLAlchemy, Alembic, `logging`, `contextvars`, React (Vite), Tailwind, Vitest.

## Global Constraints

- Format switch keyed on `os.getenv("APP_ENV") == "production"` (JSON) else plain — matches existing env checks in `web/tenancy.py`, `web/main.py`.
- `error_events` is a **global infra table** (like `config`): admin-only, NOT tenant-scoped. Do NOT add it to `_TENANT_TABLES` in `db/events.py`; `profile_id` is a plain context column, not a tenancy partition.
- Logging must NEVER cascade-fail: the DB handler swallows all exceptions; `setup_logging()` must not raise.
- The DB handler writes in its OWN short-lived `SessionLocal()` session — never a request/tenant session.
- Timestamps stored as ISO-8601 UTC strings (`datetime.now(timezone.utc).isoformat()`) to match the `String`-typed timestamp convention in `extension_token`/other tables.
- New env vars: `ERROR_LOG_MAX_ROWS` (default 1000), `ERROR_LOG_MAX_AGE_DAYS` (default 30), `ERROR_LOG_DB` (default enabled; `"0"`/`"false"` disables).
- Admin endpoints gated by `require_real_admin` (imported from `web.routers.credits`), mounted on the existing `admin_router` (`/api/admin` prefix).
- Python: type hints, black formatting, Google-style docstrings.

---

## File Structure

- `core/log_context.py` **(new)** — contextvar bag + `bind()`/`clear()`/`snapshot()` + `ContextFilter`.
- `core/logging_config.py` **(modify)** — `JsonFormatter`, env-based formatter choice, attach `ContextFilter` + `DbErrorHandler`.
- `core/error_sink.py` **(new)** — `DbErrorHandler` (fingerprint, dedup, prune, own session, swallow).
- `db/database.py` **(modify)** — `ErrorEvent` model.
- `alembic/versions/aa14errlog01_add_error_events.py` **(new)** — migration.
- `web/middleware_request_context.py` **(new)** — `RequestContextMiddleware`.
- `web/main.py` **(modify)** — register middleware; unhandled-exception handler.
- `web/routers/admin.py` **(modify)** — list/detail/clear endpoints.
- `react-dashboard/src/api.js` **(modify)** — `getErrors`, `getErrorDetail`, `clearErrors`.
- `react-dashboard/src/components/admin/ErrorLog.jsx` **(new)** — viewer panel.
- `react-dashboard/src/components/AdminPage.jsx` **(modify)** — add nav entry + mount.
- Tests: `tests/core/test_log_context.py`, `tests/core/test_json_formatter.py`, `tests/core/test_error_sink.py`, `tests/web/test_request_context_mw.py`, `tests/web/test_admin_errors.py`, `react-dashboard/src/components/admin/ErrorLog.test.jsx`.

---

## Task 1: Log context bag + filter

**Files:**
- Create: `core/log_context.py`
- Test: `tests/core/test_log_context.py`

**Interfaces:**
- Produces:
  - `bind(**fields) -> None` — set any of `request_id`/`route`/`profile_id` on the current context.
  - `clear() -> None` — reset the bag to empty.
  - `snapshot() -> dict[str, object]` — current `{request_id, route, profile_id}` (missing → `None`).
  - `ContextFilter(logging.Filter)` — injects `record.request_id/route/profile_id` from `snapshot()`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_log_context.py
import logging

from core.log_context import ContextFilter, bind, clear, snapshot


def test_snapshot_defaults_to_none():
    clear()
    assert snapshot() == {"request_id": None, "route": None, "profile_id": None}


def test_bind_then_snapshot():
    clear()
    bind(request_id="abc", route="/api/x", profile_id=7)
    assert snapshot() == {"request_id": "abc", "route": "/api/x", "profile_id": 7}
    clear()
    assert snapshot()["request_id"] is None


def test_filter_injects_attributes():
    clear()
    bind(request_id="rid", route="/r", profile_id=3)
    rec = logging.LogRecord("n", logging.ERROR, __file__, 1, "msg", None, None)
    assert ContextFilter().filter(rec) is True
    assert rec.request_id == "rid"
    assert rec.route == "/r"
    assert rec.profile_id == 3
    clear()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/core/test_log_context.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.log_context'`

- [ ] **Step 3: Write minimal implementation**

```python
# core/log_context.py
"""Request-scoped logging context.

A ``contextvars``-backed bag of ``request_id``/``route``/``profile_id`` plus a
``logging.Filter`` that copies the current values onto every ``LogRecord`` so any
log line — request-scoped or background-thread — carries whatever context is
bound at emit time.
"""
from __future__ import annotations

import contextvars
import logging

_FIELDS = ("request_id", "route", "profile_id")

_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "log_request_id", default=None
)
_route: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "log_route", default=None
)
_profile_id: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "log_profile_id", default=None
)

_VARS = {"request_id": _request_id, "route": _route, "profile_id": _profile_id}


def bind(**fields: object) -> None:
    """Set any subset of ``request_id``/``route``/``profile_id`` on the context."""
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/core/test_log_context.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add core/log_context.py tests/core/test_log_context.py
git commit -m "[feat] Add request-scoped logging context bag + filter"
```

---

## Task 2: JSON formatter + env-based selection

**Files:**
- Modify: `core/logging_config.py`
- Test: `tests/core/test_json_formatter.py`

**Interfaces:**
- Consumes: `core.log_context.ContextFilter` (Task 1).
- Produces:
  - `JsonFormatter(logging.Formatter)` — `format()` returns a JSON line with keys `ts, level, logger, msg, route, profile_id, request_id` and (when `exc_info` present) `exc_info` as a rendered traceback string.
  - `_console_formatter() -> logging.Formatter` — returns `JsonFormatter` when `APP_ENV=production`, else the plain `logging.Formatter(_FMT)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_json_formatter.py
import json
import logging

from core.logging_config import JsonFormatter


def _record(**kw):
    rec = logging.LogRecord("mylogger", logging.ERROR, __file__, 1, "boom", None, None)
    for k, v in kw.items():
        setattr(rec, k, v)
    return rec


def test_json_formatter_basic_fields():
    out = json.loads(JsonFormatter().format(_record(route="/r", profile_id=2, request_id="x")))
    assert out["level"] == "ERROR"
    assert out["logger"] == "mylogger"
    assert out["msg"] == "boom"
    assert out["route"] == "/r"
    assert out["profile_id"] == 2
    assert out["request_id"] == "x"
    assert "ts" in out
    assert "exc_info" not in out


def test_json_formatter_includes_traceback():
    try:
        raise ValueError("nope")
    except ValueError:
        import sys
        rec = logging.LogRecord(
            "l", logging.ERROR, __file__, 1, "failed", None, sys.exc_info()
        )
    out = json.loads(JsonFormatter().format(rec))
    assert "ValueError: nope" in out["exc_info"]


def test_json_formatter_missing_context_is_none():
    out = json.loads(JsonFormatter().format(_record()))
    assert out["route"] is None
    assert out["profile_id"] is None
    assert out["request_id"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/core/test_json_formatter.py -v`
Expected: FAIL with `ImportError: cannot import name 'JsonFormatter'`

- [ ] **Step 3: Write minimal implementation**

Add near the top of `core/logging_config.py` (after the existing `import` block, keeping `from __future__ import annotations` first). Add `import json` and `from datetime import datetime, timezone` to the imports, then:

```python
class JsonFormatter(logging.Formatter):
    """Render a ``LogRecord`` as a single-line JSON object for Railway ingestion."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "route": getattr(record, "route", None),
            "profile_id": getattr(record, "profile_id", None),
            "request_id": getattr(record, "request_id", None),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def _console_formatter() -> logging.Formatter:
    """JSON formatter in production, plain formatter otherwise."""
    if os.environ.get("APP_ENV") == "production":
        return JsonFormatter()
    return logging.Formatter(_FMT)
```

Then, in `setup_logging()`, change the console handler wiring. Replace:

```python
    formatter = logging.Formatter(_FMT)

    console = logging.StreamHandler(stream=sys.stdout)
    console.setFormatter(formatter)
    root.addHandler(console)
```

with:

```python
    formatter = logging.Formatter(_FMT)  # plain formatter for the rotating file

    from core.log_context import ContextFilter

    context_filter = ContextFilter()

    console = logging.StreamHandler(stream=sys.stdout)
    console.setFormatter(_console_formatter())
    console.addFilter(context_filter)
    root.addHandler(console)
```

(The file handler further down keeps using `formatter`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/core/test_json_formatter.py tests/core/test_log_context.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/logging_config.py tests/core/test_json_formatter.py
git commit -m "[feat] Add JSON log formatter selected by APP_ENV"
```

---

## Task 3: Request-context middleware

**Files:**
- Create: `web/middleware_request_context.py`
- Modify: `web/main.py`
- Test: `tests/web/test_request_context_mw.py`

**Interfaces:**
- Consumes: `core.log_context.bind`/`clear` (Task 1).
- Produces: `RequestContextMiddleware(BaseHTTPMiddleware)` — binds `request_id` (uuid4 hex), `route` (matched path template if available else raw path), and `profile_id` (from `request.session["account_id"]`→account when resolvable, else `None`), sets `X-Request-ID` response header, clears context in `finally`.

Note on `profile_id`: the tenancy seam is a FastAPI dependency, not callable from middleware without a DB session. To keep the middleware dependency-free and non-failing, resolve `profile_id` cheaply: read `request.session.get("account_id")`, look up the account's `profile_id` in a throwaway session, swallow any error → `None`. Outside production (no session), leave `profile_id` `None` — request logs still carry `request_id`/`route`.

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_request_context_mw.py
from fastapi import FastAPI
from starlette.testclient import TestClient

from web.middleware_request_context import RequestContextMiddleware
from core import log_context


def _app():
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/ping")
    def ping():
        # Context is bound during the request; capture it.
        return log_context.snapshot()

    return app


def test_binds_request_id_and_route_and_sets_header():
    client = TestClient(_app())
    resp = client.get("/ping")
    body = resp.json()
    assert body["request_id"]
    assert body["route"] == "/ping"
    assert resp.headers["x-request-id"] == body["request_id"]


def test_context_cleared_after_request():
    client = TestClient(_app())
    client.get("/ping")
    assert log_context.snapshot()["request_id"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/web/test_request_context_mw.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'web.middleware_request_context'`

- [ ] **Step 3: Write minimal implementation**

```python
# web/middleware_request_context.py
"""Bind per-request logging context (request id, route, profile) for every request."""
from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from core import log_context


def _resolve_profile_id(request: Request) -> int | None:
    """Best-effort profile id from the session; never raises."""
    try:
        account_id = request.session.get("account_id")
    except (AssertionError, KeyError, AttributeError):
        return None  # SessionMiddleware not installed / no session
    if not account_id:
        return None
    try:
        from db.database import Account, SessionLocal

        db = SessionLocal()
        try:
            acct = db.query(Account).filter_by(id=account_id).first()
            return acct.profile_id if acct else None
        finally:
            db.close()
    except Exception:
        return None


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Populate ``core.log_context`` for the duration of each request."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = uuid.uuid4().hex
        route = request.scope.get("path", "")
        log_context.bind(
            request_id=request_id,
            route=route,
            profile_id=_resolve_profile_id(request),
        )
        try:
            response = await call_next(request)
        finally:
            # Snapshot before clearing so the header still reflects this request.
            log_context.clear()
        response.headers["X-Request-ID"] = request_id
        return response
```

Then register it in `web/main.py`. After the `app.add_middleware(ImpersonationReadOnlyMiddleware)` line (so it runs inside `SessionMiddleware` and can read the session), add:

```python
from web.middleware_request_context import RequestContextMiddleware
app.add_middleware(RequestContextMiddleware)
```

Place the import with the other middleware imports near line 44-45 and the `add_middleware` call within the middleware block (before `SessionMiddleware`, which must remain outermost/last).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/web/test_request_context_mw.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add web/middleware_request_context.py web/main.py tests/web/test_request_context_mw.py
git commit -m "[feat] Bind request id/route/profile logging context per request"
```

---

## Task 4: error_events model + migration

**Files:**
- Modify: `db/database.py`
- Create: `alembic/versions/aa14errlog01_add_error_events.py`
- Test: `tests/core/test_error_events_model.py`

**Interfaces:**
- Produces: `ErrorEvent(Base)` with columns `id, created_at, last_seen, count, level, logger, message, traceback, route, profile_id, request_id, fingerprint`; `__tablename__ = "error_events"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_error_events_model.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.database import Base, ErrorEvent


def test_error_event_roundtrip():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[ErrorEvent.__table__])
    Session = sessionmaker(bind=engine)
    db = Session()
    ev = ErrorEvent(
        created_at="2026-07-23T00:00:00+00:00",
        last_seen="2026-07-23T00:00:00+00:00",
        count=1,
        level="ERROR",
        logger="x",
        message="boom",
        traceback="Traceback...",
        route="/r",
        profile_id=2,
        request_id="rid",
        fingerprint="fp",
    )
    db.add(ev)
    db.commit()
    got = db.query(ErrorEvent).one()
    assert got.fingerprint == "fp"
    assert got.count == 1
    db.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/core/test_error_events_model.py -v`
Expected: FAIL with `ImportError: cannot import name 'ErrorEvent'`

- [ ] **Step 3: Write minimal implementation**

Add to `db/database.py` after the `Config` class (keeps infra tables together):

```python
class ErrorEvent(Base):
    """Global operational log of ERROR-level events (admin-only, NOT tenant-scoped).

    Populated by ``core.error_sink.DbErrorHandler``. ``profile_id`` is a plain
    context column, not a tenancy partition — do not add this table to the
    ``before_flush`` tenant guard.
    """

    __tablename__ = "error_events"
    id = Column(Integer, primary_key=True)
    created_at = Column(String, nullable=False)
    last_seen = Column(String, nullable=False)
    count = Column(Integer, nullable=False, default=1)
    level = Column(String, nullable=False)
    logger = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    traceback = Column(Text, nullable=True)
    route = Column(String, nullable=True)
    profile_id = Column(Integer, nullable=True)
    request_id = Column(String, nullable=True)
    fingerprint = Column(String, nullable=False, index=True)
```

Create the migration:

```python
# alembic/versions/aa14errlog01_add_error_events.py
"""add error_events

Revision ID: aa14errlog01
Revises: aa13applyplan01
Create Date: 2026-07-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "aa14errlog01"
down_revision: Union[str, Sequence[str], None] = "aa13applyplan01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "error_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("last_seen", sa.String(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("level", sa.String(), nullable=False),
        sa.Column("logger", sa.String(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("traceback", sa.Text(), nullable=True),
        sa.Column("route", sa.String(), nullable=True),
        sa.Column("profile_id", sa.Integer(), nullable=True),
        sa.Column("request_id", sa.String(), nullable=True),
        sa.Column("fingerprint", sa.String(), nullable=False),
    )
    op.create_index("ix_error_events_fingerprint", "error_events", ["fingerprint"])
    op.create_index("ix_error_events_created_at", "error_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_error_events_created_at", table_name="error_events")
    op.drop_index("ix_error_events_fingerprint", table_name="error_events")
    op.drop_table("error_events")
```

- [ ] **Step 4: Run test + verify migration applies**

Run: `python -m pytest tests/core/test_error_events_model.py -v`
Expected: PASS

Run: `python -m alembic upgrade head`
Expected: applies `aa14errlog01` with no error (verify `alembic heads` now prints `aa14errlog01 (head)`).

- [ ] **Step 5: Commit**

```bash
git add db/database.py alembic/versions/aa14errlog01_add_error_events.py tests/core/test_error_events_model.py
git commit -m "[feat] Add error_events table + migration"
```

---

## Task 5: DbErrorHandler (persist, dedup, prune)

**Files:**
- Create: `core/error_sink.py`
- Modify: `core/logging_config.py`
- Test: `tests/core/test_error_sink.py`

**Interfaces:**
- Consumes: `db.database.ErrorEvent`, `SessionLocal` (Task 4).
- Produces:
  - `fingerprint(record) -> str` — sha1 of `logger + exception type + normalized top traceback frame` (line numbers stripped).
  - `DbErrorHandler(logging.Handler)` — on `emit`, upsert-by-fingerprint (increment `count`/bump `last_seen` if an in-window row exists, else insert), then prune to `ERROR_LOG_MAX_ROWS`/`ERROR_LOG_MAX_AGE_DAYS`. Never raises.
  - `install_db_error_handler(root: logging.Logger) -> None` — attach at `ERROR` level unless `ERROR_LOG_DB` disables it.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_error_sink.py
import logging

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import db.database as dbmod
from db.database import Base, ErrorEvent
from core.error_sink import DbErrorHandler, fingerprint


@pytest.fixture
def sink(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[ErrorEvent.__table__])
    TestSession = sessionmaker(bind=engine)
    monkeypatch.setattr(dbmod, "SessionLocal", TestSession)
    return TestSession


def _emit(msg, exc=None):
    handler = DbErrorHandler()
    rec = logging.LogRecord("l", logging.ERROR, __file__, 1, msg, None, exc)
    handler.emit(rec)


def test_emit_inserts_row(sink):
    _emit("boom")
    db = sink()
    assert db.query(ErrorEvent).count() == 1
    assert db.query(ErrorEvent).one().message == "boom"
    db.close()


def test_identical_errors_dedup_and_increment(sink):
    try:
        raise ValueError("x")
    except ValueError:
        import sys
        info = sys.exc_info()
    _emit("boom", info)
    _emit("boom", info)
    db = sink()
    rows = db.query(ErrorEvent).all()
    assert len(rows) == 1
    assert rows[0].count == 2
    db.close()


def test_prune_respects_max_rows(monkeypatch, sink):
    monkeypatch.setenv("ERROR_LOG_MAX_ROWS", "3")
    for i in range(6):
        _emit(f"msg-{i}")  # distinct messages → distinct fingerprints
    db = sink()
    assert db.query(ErrorEvent).count() == 3
    db.close()


def test_emit_swallows_db_errors(monkeypatch):
    monkeypatch.setattr(dbmod, "SessionLocal", lambda: (_ for _ in ()).throw(RuntimeError("down")))
    _emit("boom")  # must not raise


def test_fingerprint_stable_across_line_numbers():
    fp1 = fingerprint(logging.LogRecord("l", 40, "a.py", 10, "m", None, None))
    fp2 = fingerprint(logging.LogRecord("l", 40, "a.py", 99, "m", None, None))
    assert fp1 == fp2  # message-only fingerprint ignores lineno
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/core/test_error_sink.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.error_sink'`

- [ ] **Step 3: Write minimal implementation**

```python
# core/error_sink.py
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
from datetime import datetime, timedelta, timezone

_ADDR_RE = re.compile(r"0x[0-9a-fA-F]+")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def fingerprint(record: logging.LogRecord) -> str:
    """Stable dedup key: logger + exception type + normalized top frame / message."""
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
    raw = "|".join(_ADDR_RE.sub("0xADDR", p) for p in parts)
    return hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()


def _max_rows() -> int:
    try:
        return int(os.environ.get("ERROR_LOG_MAX_ROWS", "1000"))
    except ValueError:
        return 1000


def _max_age_days() -> int:
    try:
        return int(os.environ.get("ERROR_LOG_MAX_AGE_DAYS", "30"))
    except ValueError:
        return 30


class DbErrorHandler(logging.Handler):
    """Write ERROR records to ``error_events`` (dedup + prune). Never raises."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._emit(record)
        except Exception:  # logging must never cascade-fail
            pass

    def _emit(self, record: logging.LogRecord) -> None:
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
                existing.route = getattr(record, "route", None)
                existing.profile_id = getattr(record, "profile_id", None)
                existing.request_id = getattr(record, "request_id", None)
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
                        fingerprint=fp,
                    )
                )
            db.commit()
            self._prune(db)
        finally:
            db.close()

    def format_traceback(self, record: logging.LogRecord) -> str | None:
        if not record.exc_info:
            return None
        import traceback

        return "".join(traceback.format_exception(*record.exc_info))

    def _prune(self, db) -> None:
        from db.database import ErrorEvent

        cutoff = (datetime.now(timezone.utc) - timedelta(days=_max_age_days())).isoformat()
        db.query(ErrorEvent).filter(ErrorEvent.created_at < cutoff).delete(
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
```

Wire it into `setup_logging()` in `core/logging_config.py`, near the end just before `_CONFIGURED = True`:

```python
    try:
        from core.error_sink import install_db_error_handler

        install_db_error_handler(root)
    except Exception:  # never let logging setup fail on the DB sink
        root.warning("Could not install DB error handler", exc_info=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/core/test_error_sink.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add core/error_sink.py core/logging_config.py tests/core/test_error_sink.py
git commit -m "[feat] Persist ERROR logs to error_events with dedup + prune"
```

---

## Task 6: Unhandled request exceptions → logged with context

**Files:**
- Modify: `web/main.py`
- Test: `tests/web/test_unhandled_exception_logged.py`

**Interfaces:**
- Consumes: request context (Task 3), DB sink (Task 5).
- Produces: a global `Exception` handler that `logger.exception`s (so the record flows through `DbErrorHandler`) then re-raises via Starlette's default 500 response.

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_unhandled_exception_logged.py
import logging


def test_unhandled_exception_is_logged(caplog):
    # Import the module-level handler function and exercise it directly.
    import asyncio

    from web.main import _log_unhandled_exception

    class Boom(Exception):
        pass

    req = type("R", (), {"scope": {"path": "/api/x"}})()
    with caplog.at_level(logging.ERROR):
        try:
            asyncio.get_event_loop().run_until_complete(
                _log_unhandled_exception(req, Boom("kaboom"))
            )
        except Boom:
            pass
    assert any("kaboom" in r.getMessage() or r.exc_info for r in caplog.records)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/web/test_unhandled_exception_logged.py -v`
Expected: FAIL with `ImportError: cannot import name '_log_unhandled_exception'`

- [ ] **Step 3: Write minimal implementation**

In `web/main.py`, alongside the existing `@app.exception_handler(InsufficientCredits)` block, add a module-level logger and a catch-all handler. Near the top imports add `import logging` (if absent) and after the app is created:

```python
logger = logging.getLogger("web.unhandled")


@app.exception_handler(Exception)
async def _log_unhandled_exception(request, exc: Exception):
    logger.exception(
        "Unhandled exception on %s", request.scope.get("path", "?"), exc_info=exc
    )
    # Re-raise so Starlette produces its standard 500 response.
    raise exc
```

Note: the `RequestContextMiddleware` (Task 3) has already bound `request_id`/`route`/`profile_id` by the time this runs, so the logged record — and its `error_events` row — carry request context.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/web/test_unhandled_exception_logged.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/main.py tests/web/test_unhandled_exception_logged.py
git commit -m "[feat] Log unhandled request exceptions with request context"
```

---

## Task 7: Admin API — list / detail / clear

**Files:**
- Modify: `web/routers/admin.py`
- Test: `tests/web/test_admin_errors.py`

**Interfaces:**
- Consumes: `ErrorEvent` (Task 4), `require_real_admin`, `get_db`.
- Produces:
  - `GET /api/admin/errors?level=&route=&profile_id=&since=&limit=` → `{errors: [{id, level, logger, message, route, profile_id, request_id, count, created_at, last_seen}], total}` — grouped rows already stored deduped; ordered by `last_seen` desc.
  - `GET /api/admin/errors/{id}` → full row incl. `traceback`.
  - `DELETE /api/admin/errors?before=&level=` → `{deleted: n}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_admin_errors.py
# Assumes the repo's existing admin-test harness fixtures. Follow the pattern in
# tests/web/test_admin_set_tier.py's replacement / test_credits_api.py for building
# an authed admin TestClient + seeding rows. Minimal shape:
from db.database import ErrorEvent


def _seed(db):
    db.add(ErrorEvent(
        created_at="2026-07-23T00:00:00+00:00", last_seen="2026-07-23T00:00:00+00:00",
        count=3, level="ERROR", logger="x", message="boom", traceback="TB",
        route="/api/x", profile_id=2, request_id="rid", fingerprint="fp1",
    ))
    db.commit()


def test_list_errors_admin_only(admin_client, non_admin_client, db_session):
    _seed(db_session)
    assert non_admin_client.get("/api/admin/errors").status_code == 403
    resp = admin_client.get("/api/admin/errors")
    assert resp.status_code == 200
    body = resp.json()
    assert body["errors"][0]["message"] == "boom"
    assert body["errors"][0]["count"] == 3
    assert "traceback" not in body["errors"][0]  # list omits traceback


def test_detail_includes_traceback(admin_client, db_session):
    _seed(db_session)
    eid = db_session.query(ErrorEvent).one().id
    resp = admin_client.get(f"/api/admin/errors/{eid}")
    assert resp.status_code == 200
    assert resp.json()["traceback"] == "TB"


def test_filter_by_level(admin_client, db_session):
    _seed(db_session)
    assert admin_client.get("/api/admin/errors?level=WARNING").json()["errors"] == []


def test_clear_errors(admin_client, db_session):
    _seed(db_session)
    assert admin_client.delete("/api/admin/errors").json()["deleted"] == 1
    assert db_session.query(ErrorEvent).count() == 0
```

If the repo's admin test fixtures differ, adapt the client/session fixtures to the
existing pattern in `tests/web/` (grep for `require_real_admin` overrides in
`tests/web/conftest.py` or `test_credits_api.py`) — keep the four assertions.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/web/test_admin_errors.py -v`
Expected: FAIL (404 on the routes / import errors)

- [ ] **Step 3: Write minimal implementation**

Add to `web/routers/admin.py` (imports: `from db.database import ErrorEvent`; `Query` from fastapi):

```python
@router.get("/errors")
def list_errors(
    level: str | None = Query(None),
    route: str | None = Query(None),
    profile_id: int | None = Query(None),
    since: str | None = Query(None),
    limit: int = Query(200, le=1000),
    db: Session = Depends(get_db),
    admin: Account = Depends(require_real_admin),
):
    """List deduped error rows (newest first), traceback omitted."""
    q = db.query(ErrorEvent)
    if level:
        q = q.filter(ErrorEvent.level == level)
    if route:
        q = q.filter(ErrorEvent.route == route)
    if profile_id is not None:
        q = q.filter(ErrorEvent.profile_id == profile_id)
    if since:
        q = q.filter(ErrorEvent.last_seen >= since)
    total = q.count()
    rows = q.order_by(ErrorEvent.last_seen.desc()).limit(limit).all()
    return {
        "total": total,
        "errors": [
            {
                "id": r.id,
                "level": r.level,
                "logger": r.logger,
                "message": r.message,
                "route": r.route,
                "profile_id": r.profile_id,
                "request_id": r.request_id,
                "count": r.count,
                "created_at": r.created_at,
                "last_seen": r.last_seen,
            }
            for r in rows
        ],
    }


@router.get("/errors/{error_id}")
def get_error(
    error_id: int,
    db: Session = Depends(get_db),
    admin: Account = Depends(require_real_admin),
):
    """Full error row including traceback and all context."""
    r = db.query(ErrorEvent).filter_by(id=error_id).first()
    if r is None:
        raise HTTPException(status_code=404, detail="not found")
    return {
        "id": r.id, "level": r.level, "logger": r.logger, "message": r.message,
        "traceback": r.traceback, "route": r.route, "profile_id": r.profile_id,
        "request_id": r.request_id, "count": r.count,
        "created_at": r.created_at, "last_seen": r.last_seen,
    }


@router.delete("/errors")
def clear_errors(
    before: str | None = Query(None),
    level: str | None = Query(None),
    db: Session = Depends(get_db),
    admin: Account = Depends(require_real_admin),
):
    """Delete error rows (optionally narrowed by ``before`` last_seen / ``level``)."""
    q = db.query(ErrorEvent)
    if before:
        q = q.filter(ErrorEvent.last_seen < before)
    if level:
        q = q.filter(ErrorEvent.level == level)
    deleted = q.delete(synchronize_session=False)
    db.commit()
    return {"deleted": deleted}
```

Verify `HTTPException` and `Query` are imported at the top of `admin.py` (add to the existing `from fastapi import ...` line if missing).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/web/test_admin_errors.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add web/routers/admin.py tests/web/test_admin_errors.py
git commit -m "[feat] Add admin errors list/detail/clear endpoints"
```

---

## Task 8: Frontend Errors panel

**Files:**
- Modify: `react-dashboard/src/api.js`
- Create: `react-dashboard/src/components/admin/ErrorLog.jsx`
- Modify: `react-dashboard/src/components/AdminPage.jsx`
- Test: `react-dashboard/src/components/admin/ErrorLog.test.jsx`

**Interfaces:**
- Consumes: `GET/DELETE /api/admin/errors*` (Task 7).
- Produces: `getErrors(params)`, `getErrorDetail(id)`, `clearErrors()` in `api.js`; `ErrorLog` component; `errors` nav entry in `AdminPage`.

- [ ] **Step 1: Write the failing test**

```jsx
// react-dashboard/src/components/admin/ErrorLog.test.jsx
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import ErrorLog from './ErrorLog'
import * as api from '../../api'

describe('ErrorLog', () => {
  it('renders grouped error rows with count', async () => {
    vi.spyOn(api, 'getErrors').mockResolvedValue({
      total: 1,
      errors: [{
        id: 1, level: 'ERROR', logger: 'x', message: 'boom',
        route: '/api/x', profile_id: 2, count: 5,
        created_at: '2026-07-23T00:00:00+00:00', last_seen: '2026-07-23T00:00:00+00:00',
      }],
    })
    render(<ErrorLog />)
    await waitFor(() => expect(screen.getByText('boom')).toBeInTheDocument())
    expect(screen.getByText('/api/x')).toBeInTheDocument()
    expect(screen.getByText(/×\s*5/)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd react-dashboard && npx vitest run src/components/admin/ErrorLog.test.jsx`
Expected: FAIL (cannot resolve `./ErrorLog`)

- [ ] **Step 3: Write minimal implementation**

Add to `react-dashboard/src/api.js` (follow the existing `_fetch`/export style in that file):

```javascript
export function getErrors(params = {}) {
  const qs = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== '' && v != null)
  ).toString()
  return _fetch(`/api/admin/errors${qs ? `?${qs}` : ''}`)
}
export function getErrorDetail(id) {
  return _fetch(`/api/admin/errors/${id}`)
}
export function clearErrors() {
  return _fetch('/api/admin/errors', { method: 'DELETE' })
}
```

Create `react-dashboard/src/components/admin/ErrorLog.jsx` — a filter bar (level/route/profile/since), a grouped table (last_seen, level, route, profile, message, ×count), row-click to expand `getErrorDetail` traceback, and a "Clear all" button calling `clearErrors`. Match `ManageUsers.jsx`'s styling conventions (Tailwind, `text-space-*` palette, dark theme). Minimal working version:

```jsx
import { useState, useEffect } from 'react'
import { getErrors, getErrorDetail, clearErrors } from '../../api'

export default function ErrorLog() {
  const [rows, setRows] = useState([])
  const [filters, setFilters] = useState({ level: '', route: '', profile_id: '', since: '' })
  const [detail, setDetail] = useState(null)

  const load = () => getErrors(filters).then((d) => setRows(d.errors || []))
  useEffect(() => { load() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const expand = async (id) => {
    if (detail?.id === id) return setDetail(null)
    setDetail(await getErrorDetail(id))
  }

  return (
    <div className="space-y-4">
      <div className="flex items-end gap-3 flex-wrap">
        <input className="bg-[#1a1a2e] px-2 py-1 rounded text-sm" placeholder="level"
          value={filters.level} onChange={(e) => setFilters({ ...filters, level: e.target.value })} />
        <input className="bg-[#1a1a2e] px-2 py-1 rounded text-sm" placeholder="route"
          value={filters.route} onChange={(e) => setFilters({ ...filters, route: e.target.value })} />
        <input className="bg-[#1a1a2e] px-2 py-1 rounded text-sm" placeholder="profile id"
          value={filters.profile_id} onChange={(e) => setFilters({ ...filters, profile_id: e.target.value })} />
        <button className="text-purple-400 hover:underline text-sm" onClick={load}>Apply</button>
        <button className="text-red-400 hover:underline text-sm ml-auto"
          onClick={() => clearErrors().then(load)}>Clear all</button>
      </div>
      <table className="w-full text-sm">
        <thead className="text-space-dim text-left">
          <tr><th>Last seen</th><th>Level</th><th>Route</th><th>Profile</th><th>Message</th><th>×</th></tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <>
              <tr key={r.id} className="cursor-pointer hover:bg-[#1a1a2e]" onClick={() => expand(r.id)}>
                <td>{r.last_seen}</td><td>{r.level}</td><td>{r.route}</td>
                <td>{r.profile_id ?? '—'}</td><td className="truncate max-w-md">{r.message}</td>
                <td>×{r.count}</td>
              </tr>
              {detail?.id === r.id && (
                <tr key={`${r.id}-d`}><td colSpan={6}>
                  <pre className="text-xs overflow-x-auto bg-black/30 p-2 rounded whitespace-pre-wrap">
                    {detail.traceback || '(no traceback)'}
                    {`\nrequest_id: ${detail.request_id ?? '—'}`}
                  </pre>
                </td></tr>
              )}
            </>
          ))}
        </tbody>
      </table>
      {rows.length === 0 && <p className="text-space-dim text-sm">No errors recorded.</p>}
    </div>
  )
}
```

Wire into `react-dashboard/src/components/AdminPage.jsx`: import `ErrorLog`, add `{ key: 'errors', label: 'Error Log' }` to `FUNCTIONS`, and add `{active === 'errors' && <ErrorLog />}` in the section block.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd react-dashboard && npx vitest run src/components/admin/ErrorLog.test.jsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add react-dashboard/src/api.js react-dashboard/src/components/admin/ErrorLog.jsx react-dashboard/src/components/AdminPage.jsx react-dashboard/src/components/admin/ErrorLog.test.jsx
git commit -m "[feat] Add admin Error Log viewer panel"
```

---

## Task 9: Full-suite verification + docs

**Files:**
- Modify: `web/CONTEXT.md`, `core/CONTEXT.md`, `db/CONTEXT.md`, `.claude/CLAUDE.md` (routing row), `.claude/TODO.md`.

- [ ] **Step 1: Run full backend suite**

Run: `python -m pytest -q`
Expected: all pass (note any pre-existing order-dependent flakes documented in TODO Bugs — `test_runner.py::test_run_scraper_continues_on_source_error`, `api.profileTree.test.js` — are unrelated).

- [ ] **Step 2: Run full frontend suite**

Run: `cd react-dashboard && npx vitest run`
Expected: pass (except the known pre-existing `api.profileTree` flake).

- [ ] **Step 3: Update docs**

- `.claude/CLAUDE.md`: add/extend the logging routing row to mention `core/log_context.py`, `core/error_sink.py`, `web/middleware_request_context.py`, the `error_events` table, and the admin viewer.
- `web/CONTEXT.md`: document `RequestContextMiddleware` (middleware order: inside SessionMiddleware) + the `/api/admin/errors*` endpoints.
- `core/CONTEXT.md`: document JSON-vs-plain formatter selection, `ContextFilter`, `DbErrorHandler` (own session, dedup, prune, swallow), and the new env vars.
- `db/CONTEXT.md`: document `error_events` as a global infra table (not tenant-scoped, excluded from the `before_flush` guard).
- `.claude/TODO.md`: mark "Robust error logging for Railway (hosted)" done; note the deferred v2 items now shipped.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "[docs] Document error observability system + mark TODO done"
```

---

## Self-Review Notes

- **Spec coverage:** §1 JSON format → T2; §2 context enrichment → T1+T3; §3 DB table → T4, handler/dedup/prune → T5, unhandled-exception path → T6; §4 admin API → T7, viewer → T8; env vars → T5/T7; testing → per-task + T9. All sections mapped.
- **Non-tenant-scoping** of `error_events` enforced by the Global Constraints note + T4 docstring + T9 `db/CONTEXT.md` — not added to `_TENANT_TABLES`.
- **Type consistency:** `bind`/`clear`/`snapshot`/`ContextFilter` (T1) reused verbatim in T2/T3; `fingerprint`/`DbErrorHandler`/`install_db_error_handler` (T5) match wiring; `ErrorEvent` column names identical across T4/T5/T7. Endpoint shapes in T7 match T8 consumers (`count`, `last_seen`, `traceback` on detail only).
