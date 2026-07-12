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
    # Clear leftover handlers so tests are isolated from any prior setup_logging()
    # (e.g. another test importing web.main installs a real RotatingFileHandler).
    root.handlers[:] = []
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
    assert any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler)
        for h in root.handlers
    )


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
    fh = next(
        h for h in logging.getLogger().handlers if isinstance(h, RotatingFileHandler)
    )
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
    assert any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler)
        for h in root.handlers
    )
    assert not any(isinstance(h, RotatingFileHandler) for h in root.handlers)
