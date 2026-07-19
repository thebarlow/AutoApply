"""Startup warning when production resolves a zero default credit rate."""
from __future__ import annotations

from web.main import _warn_if_billing_disabled


def test_warns_in_production_with_zero_rate(monkeypatch, caplog):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CREDIT_DEFAULT_RATE", "0")
    with caplog.at_level("WARNING", logger="web.main"):
        _warn_if_billing_disabled()
    assert any("NOT be billed" in r.getMessage() for r in caplog.records)


def test_silent_in_production_with_positive_rate(monkeypatch, caplog):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CREDIT_DEFAULT_RATE", "1.0")
    with caplog.at_level("WARNING", logger="web.main"):
        _warn_if_billing_disabled()
    assert not caplog.records


def test_silent_outside_production(monkeypatch, caplog):
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("CREDIT_DEFAULT_RATE", "0")
    with caplog.at_level("WARNING", logger="web.main"):
        _warn_if_billing_disabled()
    assert not caplog.records
