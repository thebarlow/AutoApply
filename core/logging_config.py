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
            log_path,
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError as exc:
        root.warning(
            "Could not open log file %s (%s); logging to console only.", log_path, exc
        )

    def _thread_excepthook(args: threading.ExceptHookArgs) -> None:
        logging.getLogger(getattr(args.thread, "name", "thread")).error(
            "Uncaught exception in background thread",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    threading.excepthook = _thread_excepthook

    def _sys_excepthook(exc_type, exc_value, exc_tb) -> None:
        logging.getLogger("uncaught").error(
            "Uncaught exception", exc_info=(exc_type, exc_value, exc_tb)
        )

    sys.excepthook = _sys_excepthook

    _CONFIGURED = True
