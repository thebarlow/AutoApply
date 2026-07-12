# Structured Error Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route backend logging through Python `logging` to a size-rotating file (with full tracebacks on failures), env-configurable, while preserving current console output.

**Architecture:** A new `core/logging_config.py` exposes an idempotent `setup_logging()` that installs a stdout `StreamHandler` and a size-based `RotatingFileHandler` on the root logger, plus a `threading.excepthook`/`sys.excepthook` so uncaught background-thread exceptions land in the log with tracebacks. `setup_logging()` is called once at the top of `web/main.py` and `tray_app/main.py`. Failure-path `print(..., flush=True)` calls in the background pipeline/scraper code are converted to `logger.exception(...)` to capture tracebacks that `str(exc)` currently loses.

**Tech Stack:** Python stdlib `logging` (`RotatingFileHandler`, `threading.excepthook`), pytest.

## Global Constraints

- Python: type hints, `black` formatting, Google-style docstrings.
- Prefer stdlib — no new third-party dependencies (use `logging` only).
- Logging setup must NEVER crash startup: if the log dir/file can't be created/opened, warn to console and continue console-only.
- `setup_logging()` must be idempotent (safe to call more than once — guard against duplicate handlers).
- Rotation is **size-based**: `maxBytes=5*1024*1024`, `backupCount=5`.
- Env vars: `LOG_LEVEL` (default `INFO`), `LOG_DIR` (default repo-relative `logs/`), `LOG_FILE` (optional explicit path override; default `<LOG_DIR>/app.log`).
- Formatter: `%(asctime)s %(levelname)s [%(name)s] %(message)s`.
- Do NOT touch `job.last_result_error` semantics — it stays the short user-facing message.
- No DB table / dashboard viewer in this plan (deferred v2).

---

### Task 1: `core/logging_config.py` — `setup_logging()`

**Files:**
- Create: `core/logging_config.py`
- Test: `tests/core/test_logging_config.py`

**Interfaces:**
- Produces: `setup_logging() -> None` — idempotent; configures root logger with a stdout StreamHandler and a size-based RotatingFileHandler; installs `threading.excepthook`. Honors `LOG_LEVEL`, `LOG_DIR`, `LOG_FILE`. Never raises on log-path failure.

- [ ] **Step 1: Write the failing tests**

```python
# tests/core/test_logging_config.py
"""Tests for core.logging_config.setup_logging."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

import pytest

from core import logging_config


@pytest.fixture(autouse=True)
def _reset_logging():
    """Snapshot and restore root logger state around each test."""
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    logging_config._CONFIGURED = False
    yield
    root.handlers[:] = saved_handlers
    root.setLevel(saved_level)
    logging_config._CONFIGURED = False


def test_installs_file_and_stream_handlers(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    logging_config.setup_logging()
    root = logging.getLogger()
    kinds = {type(h) for h in root.handlers}
    assert RotatingFileHandler in kinds
    assert any(isinstance(h, logging.StreamHandler)
               and not isinstance(h, RotatingFileHandler)
               for h in root.handlers)


def test_writes_to_configured_file(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    logging_config.setup_logging()
    logging.getLogger("test.writer").error("boom-marker")
    for h in logging.getLogger().handlers:
        h.flush()
    log_file = tmp_path / "app.log"
    assert log_file.exists()
    assert "boom-marker" in log_file.read_text(encoding="utf-8")


def test_rotation_is_size_based(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    logging_config.setup_logging()
    fh = next(h for h in logging.getLogger().handlers
              if isinstance(h, RotatingFileHandler))
    assert fh.maxBytes == 5 * 1024 * 1024
    assert fh.backupCount == 5


def test_respects_log_level_env(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    logging_config.setup_logging()
    assert logging.getLogger().level == logging.WARNING


def test_idempotent_no_duplicate_handlers(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    logging_config.setup_logging()
    count = len(logging.getLogger().handlers)
    logging_config.setup_logging()
    assert len(logging.getLogger().handlers) == count


def test_unwritable_dir_falls_back_to_console(tmp_path, monkeypatch):
    # Point LOG_FILE at a path whose parent is a file, so the dir can't be made.
    bad_parent = tmp_path / "afile"
    bad_parent.write_text("x", encoding="utf-8")
    monkeypatch.setenv("LOG_FILE", str(bad_parent / "sub" / "app.log"))
    logging_config.setup_logging()  # must not raise
    root = logging.getLogger()
    assert any(isinstance(h, logging.StreamHandler)
               and not isinstance(h, RotatingFileHandler)
               for h in root.handlers)
    assert not any(isinstance(h, RotatingFileHandler) for h in root.handlers)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/core/test_logging_config.py -v`
Expected: FAIL / ERROR — `core.logging_config` has no `setup_logging` / no `_CONFIGURED`.

- [ ] **Step 3: Write the implementation**

```python
# core/logging_config.py
"""Central logging configuration for the backend.

Installs a stdout stream handler plus a size-based rotating file handler on the
root logger, and a ``threading.excepthook`` so uncaught exceptions in the
background daemon threads (intake pipeline, refinement, ATS gate) are captured
with full tracebacks. Idempotent and never raises on log-path failure.
"""
from __future__ import annotations

import logging
import os
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

_CONFIGURED = False

_FMT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
_MAX_BYTES = 5 * 1024 * 1024
_BACKUP_COUNT = 5


def _log_file_path() -> Path:
    """Resolve the target log file from ``LOG_FILE`` / ``LOG_DIR`` env vars."""
    explicit = os.environ.get("LOG_FILE")
    if explicit:
        return Path(explicit)
    log_dir = os.environ.get("LOG_DIR") or "logs"
    return Path(log_dir) / "app.log"


def setup_logging() -> None:
    """Configure root logging: console + size-rotating file, and thread hook.

    Idempotent. Honors ``LOG_LEVEL`` (default ``INFO``), ``LOG_DIR`` (default
    ``logs/``), and ``LOG_FILE`` (explicit override). If the log file cannot be
    opened, logs a warning and continues console-only rather than raising.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    level_name = (os.environ.get("LOG_LEVEL") or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)
    formatter = logging.Formatter(_FMT)

    console = logging.StreamHandler(stream=sys.stdout)
    console.setFormatter(formatter)
    root.addHandler(console)

    log_path = _log_file_path()
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_path, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError as exc:
        root.warning("Could not open log file %s (%s); logging to console only.",
                     log_path, exc)

    def _thread_excepthook(args: threading.ExceptHookArgs) -> None:
        logging.getLogger(getattr(args.thread, "name", "thread")).error(
            "Uncaught exception in background thread",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    threading.excepthook = _thread_excepthook

    def _sys_excepthook(exc_type, exc_value, exc_tb) -> None:
        logging.getLogger("uncaught").error(
            "Uncaught exception", exc_info=(exc_type, exc_value, exc_tb))

    sys.excepthook = _sys_excepthook

    _CONFIGURED = True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/core/test_logging_config.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Format**

Run: `python -m black core/logging_config.py tests/core/test_logging_config.py`
Expected: reformatted / unchanged, exit 0.

- [ ] **Step 6: Commit**

```bash
git add core/logging_config.py tests/core/test_logging_config.py
git commit -m "[feat] Add central logging config (rotating file + thread excepthook)"
```

---

### Task 2: Wire `setup_logging()` into startup + gitignore `logs/`

**Files:**
- Modify: `.gitignore` (append `logs/`)
- Modify: `web/main.py:1-17` (import block — add setup call before other imports run)
- Modify: `tray_app/main.py` (top of module / entry, before app logic)

**Interfaces:**
- Consumes: `core.logging_config.setup_logging` from Task 1.

- [ ] **Step 1: Add `logs/` to `.gitignore`**

Append under the "Test artifacts" area (exact text):

```
# Runtime logs
logs/
```

- [ ] **Step 2: Call `setup_logging()` early in `web/main.py`**

Insert immediately after `from __future__ import annotations` and the stdlib imports at the top, BEFORE the project imports (before `from db.database import init_db`), so any import-time logging is captured:

```python
from core.logging_config import setup_logging

setup_logging()
```

Place it right after line 9 (`from zoneinfo import ZoneInfo`) and before the `from fastapi import ...` block. (Import ordering: this project already interleaves third-party and local imports, so a local import here is consistent.)

- [ ] **Step 3: Call `setup_logging()` in `tray_app/main.py`**

Open `tray_app/main.py`, and near the top of the module (after its imports, before any `QApplication`/logging use), add:

```python
from core.logging_config import setup_logging

setup_logging()
```

- [ ] **Step 4: Smoke-test the server import**

Run: `python -c "import web.main; print('ok')"`
Expected: prints `ok`, and a `logs/app.log` file now exists in the repo root.

- [ ] **Step 5: Verify the file is git-ignored**

Run: `git status --porcelain logs/`
Expected: no output (the `logs/` directory is ignored).

- [ ] **Step 6: Commit**

```bash
git add .gitignore web/main.py tray_app/main.py
git commit -m "[feat] Initialize central logging at server + tray startup; ignore logs/"
```

---

### Task 3: Convert failure-path prints to `logger.exception` in `web/intake_pipeline.py`

**Files:**
- Modify: `web/intake_pipeline.py`

**Interfaces:**
- Consumes: root logging config from Task 2 (handlers already installed at import).

Add a module-level logger at the top of the file (after the imports, e.g. after line 17):

```python
import logging

logger = logging.getLogger(__name__)
```

Then convert each `except`-block failure print. The pattern: inside an `except ... as exc:` block, replace

```python
print(f"[<tag>] {job_key}: <msg> — {exc}", flush=True)
```

with

```python
logger.exception("%s: <msg>", job_key)
```

`logger.exception` records the active traceback automatically, so drop the trailing `— {exc}`. Convert exactly these call sites (line numbers approximate — match on the text):

- [ ] **Step 1: Convert the `except`-block prints**

Apply these replacements (each is inside an `except Exception as exc:` block):

1. `_emit()` — line ~72: this is a non-fatal SSE emit warning, keep it lightweight:
   - From: `print(f"[intake_pipeline] SSE emit failed for {job.job_key}: {exc}", flush=True)`
   - To: `logger.warning("SSE emit failed for %s: %s", job.job_key, exc)`
2. Section-refine eval failure — line ~247:
   - From: `print(f"[section-refine] {job_key}: eval turn {turn} failed — {exc}", flush=True)`
   - To: `logger.exception("%s: section eval turn %s failed", job_key, turn)`
3. Section-refine refine failure — line ~297:
   - From: `print(f"[section-refine] {job_key}: refine turn {turn} failed — {exc}", flush=True)`
   - To: `logger.exception("%s: section refine turn %s failed", job_key, turn)`
4. `_save_turn_snapshot` failure — line ~347:
   - From: `print(f"[refinement:{doc_type}] {job_key}: snapshot turn {n} failed: {e}", flush=True)`
   - To: `logger.exception("%s: %s snapshot turn %s failed", job_key, doc_type, n)`
5. `_restore_best` failure — line ~376:
   - From: `print(f"[refinement:{doc_type}] {job_key}: restore failed: {e}", flush=True)`
   - To: `logger.exception("%s: %s restore failed", job_key, doc_type)`
6. Doc-refine eval failure — line ~467:
   - From: `print(f"[refinement:{doc_type}] {job_key}: eval failed — {exc}", flush=True)`
   - To: `logger.exception("%s: %s eval failed", job_key, doc_type)`
7. Doc-refine rewrite failure — line ~501:
   - From: `print(f"[refinement:{doc_type}] {job_key}: rewrite failed — {exc}", flush=True)`
   - To: `logger.exception("%s: %s rewrite failed", job_key, doc_type)`
8. ATS gate failure — line ~550:
   - From: `print(f"[ats] {job_key}: gate run failed — {exc}", flush=True)`
   - To: `logger.exception("%s: ATS gate run failed", job_key)`
9. `run_resume_refinement` outer failure — line ~569:
   - From: `print(f"[refinement:resume] {job_key}: refinement failed — {exc}", flush=True)`
   - To: `logger.exception("%s: resume refinement failed", job_key)`
10. Résumé feedback refine failure — line ~650:
    - From: `print(f"[feedback:resume] {job_key}: refine failed — {exc}", flush=True)`
    - To: `logger.exception("%s: resume feedback refine failed", job_key)`
11. Post-feedback eval (résumé, non-fatal) — line ~679:
    - From: `print(f"[feedback:resume] {job_key}: post-feedback eval failed (non-fatal) — {exc}", flush=True)`
    - To: `logger.exception("%s: post-feedback resume eval failed (non-fatal)", job_key)`
12. Generic feedback refine failure — line ~774:
    - From: `print(f"[feedback:{doc_type}] {job_key}: refine failed — {exc}", flush=True)`
    - To: `logger.exception("%s: %s feedback refine failed", job_key, doc_type)`
13. Post-feedback eval (generic, non-fatal) — line ~808:
    - From: `print(f"[feedback:{doc_type}] {job_key}: post-feedback eval failed (non-fatal) — {exc}", flush=True)`
    - To: `logger.exception("%s: %s post-feedback eval failed (non-fatal)", job_key, doc_type)`

Leave the non-`except` informational prints (prompt-not-configured warnings, turn progress like `turn {turn} evaluating`, restore/complete notices) as `print` for this pass — they are out of scope.

- [ ] **Step 2: Verify no `except`-block failure prints remain**

Run: `python -m pytest tests/web/test_pipeline_failed_scrape.py -v`
Expected: PASS (existing pipeline failure test still green — behavior unchanged, only the log call differs).

- [ ] **Step 3: Confirm the module imports and logger is wired**

Run: `python -c "import web.intake_pipeline as m; print(m.logger.name)"`
Expected: prints `web.intake_pipeline`.

- [ ] **Step 4: Format**

Run: `python -m black web/intake_pipeline.py`
Expected: reformatted / unchanged, exit 0.

- [ ] **Step 5: Commit**

```bash
git add web/intake_pipeline.py
git commit -m "[refactor] Log pipeline failures with tracebacks via logging"
```

---

### Task 4: Convert failure-path prints in `core/job.py` and scrapers

**Files:**
- Modify: `core/job.py`
- Modify: `scraper/runner.py`, `scraper/search.py`, `scraper/__main__.py` (only `except`-block prints)

**Interfaces:**
- Consumes: root logging config from Task 2.

- [ ] **Step 1: Add a logger to `core/job.py`**

Near the top of `core/job.py` (after its imports), add if not already present:

```python
import logging

logger = logging.getLogger(__name__)
```

- [ ] **Step 2: Convert the intake `except`-block print in `core/job.py`**

At line ~969, inside the `except Exception as exc:` block of the `_run` intake thread:
- From: `print(f"[intake] {job_key}: extraction failed — {exc}", flush=True)`
- To: `logger.exception("%s: extraction failed", job_key)`

Leave the two informational `[intake]` prints (`extraction started`, `extraction complete`, `job not found in thread session`) as `print` — not failure paths.

- [ ] **Step 3: Convert scraper `except`-block prints**

For each of `scraper/runner.py`, `scraper/search.py`, `scraper/__main__.py`: add `import logging` + `logger = logging.getLogger(__name__)` at the top if absent, then convert ONLY prints that sit inside an `except ... as exc:`/`except ... as e:` block from `print(f"[...] ... {exc}", flush=True)` to `logger.exception("...")` (dropping the `{exc}` interpolation). Leave progress/status prints (non-except) untouched.

To locate them: run `git grep -n 'print(f"\[' scraper/` and inspect each — convert only those whose enclosing block is an `except`.

- [ ] **Step 4: Run the scraper + job tests**

Run: `python -m pytest tests/core tests/scraper tests/test_job_refinement.py -q`
Expected: PASS (no behavior change; only logging call sites changed).

- [ ] **Step 5: Format**

Run: `python -m black core/job.py scraper/`
Expected: reformatted / unchanged, exit 0.

- [ ] **Step 6: Commit**

```bash
git add core/job.py scraper/
git commit -m "[refactor] Log job/scraper failures with tracebacks via logging"
```

---

### Task 5: Manual end-to-end verification + docs

**Files:**
- Modify: `TODO.md` (mark the structured-error-logging item done, note v2 deferral)
- Read/verify: `logs/app.log`

- [ ] **Step 1: Trigger a real background failure and confirm traceback lands in the file**

Start the server (`start.bat` or `python -m uvicorn web.main:app --port 8080`), induce an intake failure (e.g. stage a job with a description that forces an extraction error, or temporarily set an invalid model), then:

Run: `tail -n 40 logs/app.log`
Expected: a `... ERROR [web.intake_pipeline] <job_key>: ... failed` line followed by a full multi-line traceback (not just the one-line message).

- [ ] **Step 2: Confirm console still shows logs**

Expected: the same failure line appears in the server console (stdout handler), matching prior visibility.

- [ ] **Step 3: Update `TODO.md`**

In the "Implement structured error logging" bullet, change `- [ ]` to `- [x]`, and append a note:

```
  **DONE (2026-07-12, v1):** central `core/logging_config.py` (`setup_logging()`)
  installs a stdout handler + size-based `RotatingFileHandler` (5MB×5) on the root
  logger and a `threading.excepthook`; wired at `web/main.py` + `tray_app/main.py`
  startup; env-configurable via `LOG_LEVEL`/`LOG_DIR`/`LOG_FILE`; `logs/` gitignored.
  Failure-path prints in the intake pipeline, `core/job.py`, and scrapers now use
  `logger.exception` (full tracebacks). Deferred v2: queryable DB error table +
  dashboard viewer.
```

- [ ] **Step 4: Commit**

```bash
git add TODO.md
git commit -m "[docs] Mark structured error logging (v1) done in TODO"
```

---

## Notes for the implementer

- The full test suite runner is `python -m pytest` from the repo root; `tests/conftest.py` provides autouse fixtures (mapper config, prompt-dir isolation).
- `logger.exception(...)` must be called from **inside an `except` block** — it reads the active exception. All conversions above are in except blocks; do not move them.
- Do not convert `print` calls that are not in except blocks in this plan — informational progress logging migration is explicitly out of scope (spec §"Out of scope").
- `job.last_result_error = str(exc)` assignments stay exactly as-is; only the adjacent print becomes a logger call.
