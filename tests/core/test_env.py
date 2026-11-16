"""core.env must fail closed: an unset APP_ENV on Railway means production."""
import pytest

from core import env


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)


def test_missing_everything_is_dev(monkeypatch):
    assert env.app_env() == env.DEVELOPMENT
    assert env.is_dev() and not env.is_production()


def test_missing_app_env_on_railway_is_production(monkeypatch):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    assert env.app_env() == env.PRODUCTION
    assert env.is_production()


def test_any_railway_runtime_var_counts(monkeypatch):
    monkeypatch.setenv("RAILWAY_SERVICE_ID", "abc")
    assert env.is_production()


def test_railway_token_alone_does_not_flip_local_dev(monkeypatch):
    # Developers keep a CLI RAILWAY_TOKEN in the local .env.
    monkeypatch.setenv("RAILWAY_TOKEN", "x")
    assert env.app_env() == env.DEVELOPMENT


def test_empty_app_env_treated_as_missing(monkeypatch):
    monkeypatch.setenv("APP_ENV", "  ")
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "p")
    assert env.is_production()


@pytest.mark.parametrize("value,expected", [
    ("production", "production"), (" Production ", "production"),
    ("development", "development"), ("test", "test"),
])
def test_valid_values(monkeypatch, value, expected):
    monkeypatch.setenv("APP_ENV", value)
    assert env.app_env() == expected


def test_explicit_development_wins_on_railway(monkeypatch):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "staging")
    monkeypatch.setenv("APP_ENV", "development")
    assert not env.is_production()


@pytest.mark.parametrize("value", ["prod", "producton", "staging", "1"])
def test_garbage_value_raises(monkeypatch, value):
    monkeypatch.setenv("APP_ENV", value)
    with pytest.raises(env.InvalidAppEnv):
        env.validate_app_env()
    with pytest.raises(env.InvalidAppEnv):
        env.is_production()


def test_web_main_import_rejects_garbage(monkeypatch):
    """A bad APP_ENV aborts web.main at import time with a clear message."""
    import importlib
    import sys

    monkeypatch.setenv("APP_ENV", "prodution")
    saved = sys.modules.pop("web.main", None)
    try:
        with pytest.raises(env.InvalidAppEnv, match="prodution"):
            importlib.import_module("web.main")
    finally:
        sys.modules.pop("web.main", None)
        if saved is not None:
            sys.modules["web.main"] = saved
