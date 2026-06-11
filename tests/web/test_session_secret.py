"""The session-signing secret must never fall back to the dev default in
production, or anyone could forge a session cookie and bypass auth."""
import pytest

from web.main import _session_secret, _DEV_SESSION_SECRET


def test_dev_uses_default_when_unset(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    assert _session_secret() == _DEV_SESSION_SECRET


def test_production_requires_secret(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    with pytest.raises(RuntimeError):
        _session_secret()


def test_production_rejects_dev_default(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SESSION_SECRET", _DEV_SESSION_SECRET)
    with pytest.raises(RuntimeError):
        _session_secret()


def test_production_accepts_real_secret(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SESSION_SECRET", "a-strong-random-value")
    assert _session_secret() == "a-strong-random-value"
