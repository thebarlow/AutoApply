# Hosted Error Observability — Design

**Date:** 2026-07-23
**Status:** Approved (design), pending implementation plan
**Branch:** `worktree-error-observability`

## Problem

Local rotating-file logging (`core/logging_config.py`, "Structured error logging v1") does
not help on the hosted Railway deployment (`https://autoapply.matthewbarlow.me`):

- The `/data` volume log file is not easily inspectable and container
  restarts/redeploys scatter context.
- Railway's hobby-tier log stream has ~7-day retention and only parses **JSON** log
  lines into structured, filterable fields — our console handler emits plain text.
- Caught-and-logged failures (e.g. résumé-parse 422, background intake/refinement
  thread crashes) are invisible without SSHing into the container.

Goal: production failures diagnosable from an in-app admin surface, durable beyond the
Railway log retention window, with structured logs in the Railway UI as a secondary view.

## Scope

Endpoint = full stack: (1) JSON log routing/format by env, (2) request-context
enrichment, (3) a durable, self-pruning DB error table, (4) an admin API + viewer with
grouping/dedup and filters.

Out of scope: alerting/paging, external log aggregators (Sentry/Datadog), non-error
(INFO/WARN) persistence, log-based metrics.

## Component 1 — Log formatting (`core/logging_config.py`)

Add a JSON formatter selected by `APP_ENV`:

- **Production** (`APP_ENV=production`): the stdout `StreamHandler` emits one JSON object
  per line: `ts`, `level`, `logger`, `msg`, `route`, `profile_id`, `request_id`, and
  `exc_info` (traceback rendered to a single joined string when present). Railway parses
  these into filterable fields.
- **Local / other**: keep the current plain formatter
  (`%(asctime)s %(levelname)s [%(name)s] %(message)s`).

Implementation: a `JsonFormatter(logging.Formatter)` whose `format()` builds a dict from
the record (pulling the enrichment attributes injected by Component 2, defaulting to
`None`) and `json.dumps`es it. A `_console_formatter()` helper returns JSON vs. plain by
env. The size-based `RotatingFileHandler` stays as-is (harmless locally, unused on
Railway). No existing `logger.exception`/`logger.error` call site changes.

## Component 2 — Request-context enrichment

- A `contextvars.ContextVar` bag holding `request_id`, `route`, `profile_id` (module e.g.
  `core/log_context.py`: getters/setters + a `bind(**kw)` helper).
- A `logging.Filter` (`ContextFilter`) added to the root handlers injects the current
  contextvar values onto every `LogRecord` as attributes, so any log line — request-scoped
  or background-thread — carries whatever context is active at emit time. Missing values
  default to `None`.
- A request middleware in `web/` (`BaseHTTPMiddleware` or pure ASGI, matching the existing
  auth-gate style): generates a `request_id` (uuid4) per request, binds
  `request_id` + `route` (the matched path template when available, else raw path), and
  binds `profile_id` from the existing `current_profile_id` seam once resolved. Sets an
  `X-Request-ID` response header. Resets the context bag in a `finally`.

## Component 3 — DB persistence (`db/` + logging handler)

### Table `error_events`

| column | type | notes |
|---|---|---|
| `id` | int PK | |
| `created_at` | datetime (UTC) | first occurrence |
| `last_seen` | datetime (UTC) | most recent occurrence |
| `count` | int | occurrences sharing this fingerprint in-window |
| `level` | str | `ERROR` / `CRITICAL` |
| `logger` | str | record logger name |
| `message` | str | formatted message |
| `traceback` | text nullable | rendered `exc_info`, if any |
| `route` | str nullable | from context |
| `profile_id` | int nullable | from context |
| `request_id` | str nullable | from context |
| `fingerprint` | str indexed | dedup key |

Alembic migration adds the table (indexes on `fingerprint`, `created_at`).

**Note on tenancy:** `error_events` is a global operational/infra table (admin-only,
like `config`), NOT tenant-scoped. `profile_id` is stored as context, not as a tenancy
partition — the `before_flush` tenant guard and `scoped()` must not apply to it. Writes
use a dedicated session (see below), keeping it outside the request's tenant-scoped
session entirely.

### Handler

A custom `logging.Handler` (`DbErrorHandler`) attached to the root logger at `ERROR`
level:

- Writes each record in its **own short-lived DB session** (never the request/tenant
  session) so it can't interfere with request transactions or the tenant guard.
- Wraps everything in try/except and swallows all exceptions (logging must never
  cascade-fail). On DB-write failure it silently drops (the stdout JSON line already
  captured it).
- **Dedup:** `fingerprint = sha1(logger + exception_type + normalized_top_app_frame)`
  (normalization strips line numbers / memory addresses so the same error dedups across
  releases). On write, if an in-window row with the same fingerprint exists, increment
  `count` and bump `last_seen` + refresh context columns instead of inserting.
- **Prune-on-insert:** delete rows older than `ERROR_LOG_MAX_AGE_DAYS` (default 30) and
  any beyond the newest `ERROR_LOG_MAX_ROWS` (default 1000). Cheap; runs on the same
  dedicated session. Bounds the table with zero maintenance.

Handler is wired in `setup_logging()` only when a DB is available (guarded so unit
contexts / early startup don't blow up); env `ERROR_LOG_DB` can force-disable.

### Unhandled request exceptions

A FastAPI exception handler (or the Component-2 middleware's try/except) calls
`logger.exception(...)` **with the context bag already bound** for any unhandled request
exception, so it flows through the same `DbErrorHandler` + JSON stream — no separate write
path. Response to the client is unchanged (500).

## Component 4 — Admin API + viewer

### API (`web/routers/admin.py`, all behind `require_real_admin`)

- `GET /api/admin/errors` — paginated, grouped-by-fingerprint rows (each carries
  `count`, `first`/`last_seen`, representative message/route/level/profile). Filters:
  `level`, `route`, `profile_id`, `since` (ISO timestamp or relative window). Reverse-chron
  by `last_seen`.
- `GET /api/admin/errors/{id}` — a single event's full traceback + all context columns.
- `DELETE /api/admin/errors` — clear all (with optional `before`/`level` narrowing).

### UI (`react-dashboard/`)

New "Errors" section in the Admin page (matches existing admin-panel styling):

- Filter bar: level, route, profile, time range.
- Reverse-chron grouped table: time (`last_seen`), level, route, profile, message, ×count.
- Row expands to full traceback + context.
- "Clear all" action.

## Testing

- **Unit:** `JsonFormatter` output shape; `ContextFilter` injection with/without bound
  context; fingerprint normalization + dedup increment; prune-on-insert row/age bounds;
  handler swallows DB errors.
- **API:** admin-only gate (403 for non-admin), filter query correctness, grouping,
  clear.
- **Integration:** an emitted `logger.exception` inside a bound request context lands one
  `error_events` row with route/profile/request_id populated; a second identical emit
  increments `count` rather than inserting.
- **Frontend:** Errors panel renders grouped rows, expands detail, applies filters.

## Env vars (new)

| var | default | purpose |
|---|---|---|
| `ERROR_LOG_MAX_ROWS` | `1000` | prune cap (rows) |
| `ERROR_LOG_MAX_AGE_DAYS` | `30` | prune cap (age) |
| `ERROR_LOG_DB` | on | force-disable DB persistence |

(`APP_ENV` already exists and drives the JSON-vs-plain formatter choice.)

## Rollout

Single deploy: Alembic migration runs on Railway startup (existing alembic-on-startup),
JSON logs begin flowing immediately, the admin viewer appears in the Admin tab. No data
backfill (errors accrue going forward).
