# Structured Error Logging — Design (v1: persistent rotating file)

**Date:** 2026-07-12
**Status:** Approved, pending implementation
**TODO ref:** `TODO.md` → Bugs → "Implement structured error logging"

## Problem

The only way to see a backend failure today is to copy-paste a traceback out of
the terminal. Failures in the background daemon threads (intake pipeline,
refinement, ATS gate) are especially easy to miss. Logging is done via ~40
scattered `print(..., flush=True)` calls with ad-hoc `[tag]` prefixes; there is
no `logging` config, no rotating file, and `except` blocks record only
`str(exc)` — the full traceback is lost.

## Goal (v1)

Route backend logging through Python `logging` to a **rotating file** with full
tracebacks on failures, configurable via env var, while preserving current
console output. Deferred to a later layer (NOT in v1): a queryable DB error
table and a dashboard error viewer.

## Design

### 1. New module: `core/logging_config.py`

A single idempotent `setup_logging()` function (guards against double-config via
a module-level flag / checking existing handlers):

- Configures the **root logger** with two handlers:
  - `StreamHandler` → stdout. Preserves current console visibility; Railway
    captures stdout in prod.
  - `RotatingFileHandler` → `<LOG_DIR>/app.log`. **Size-based rotation:**
    `maxBytes=5*1024*1024` (5 MB), `backupCount=5`.
- Formatter: `%(asctime)s %(levelname)s [%(name)s] %(message)s`.
- Configuration via env vars:
  - `LOG_LEVEL` — root level, default `INFO`.
  - `LOG_DIR` — directory for the log file, default `logs/` (repo-relative).
  - `LOG_FILE` — optional explicit file path override; if unset, `<LOG_DIR>/app.log`.
- The log directory is created if missing. If it cannot be created or the file
  handler cannot be opened, emit a warning to the console handler and continue
  **console-only** — logging setup must never crash startup.
- Installs `threading.excepthook` (and `sys.excepthook`) so uncaught exceptions
  in the background daemon threads land in the log **with tracebacks**. This is
  the single biggest win, since those threads are the motivating cases.

### 2. Call sites

- `setup_logging()` is called once at the **top of `web/main.py`** (at module
  import, before routers import anything that logs).
- Also called in `tray_app/main.py`.
- Each module that logs uses `logger = logging.getLogger(__name__)`. `__name__`
  replaces the ad-hoc `[intake_pipeline]` / `[refinement:resume]` tag prefixes
  naturally.

### 3. Convert error paths (targeted, not a full migration)

In the `except` blocks across `web/intake_pipeline.py`, `core/job.py`, and the
scrapers, replace `print(f"[tag] ... {exc}", flush=True)` with
`logger.exception("...")`, which captures the **full traceback** — the thing
`str(exc)` currently loses.

Benign informational prints (startup timings, per-turn progress) stay as `print`
for v1 — they still appear on the console. Full print→logger migration is out of
scope.

`job.last_result_error` (already persisted and surfaced to the dashboard via
SSE) is **left untouched**: it remains the short user-facing message; the log
file holds the full traceback. No DB table, no dashboard viewer in v1.

### 4. `.gitignore`

Add `logs/` so the local log file is not tracked.

## Out of scope (future v2 layer)

- Queryable DB error table (`job_key`, stage, message, traceback, timestamp).
- Dashboard error viewer.
- Full print→logger migration of benign info/debug lines.
- Railway `/data` volume persistence for the log file (stdout capture is
  sufficient in prod; `LOG_DIR` env can point at the volume if ever needed).

## Success criteria

- After a background intake/refinement failure, the full traceback is present in
  `logs/app.log` without touching the terminal.
- Console output is unchanged in content for existing prints.
- Startup never fails due to logging setup (e.g. unwritable log dir).
- `LOG_LEVEL` / `LOG_DIR` env vars control level and location.
