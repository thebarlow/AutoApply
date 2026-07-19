"""Tenant model-selection allowlist (core.llm.allowed_models / model_allowed).

Prompt-slot models run on the platform's LLM key at flat per-action prices, so
tenant-selected models must be restricted: explicit ``LLM_ALLOWED_MODELS`` wins,
production without it fails safe to the default model, and local stays open.
"""
from __future__ import annotations

from core.llm import allowed_models, get_client_for_profile, model_allowed


def _clear_env(monkeypatch):
    for var in ("LLM_ALLOWED_MODELS", "APP_ENV", "LLM_DEFAULT_MODEL"):
        monkeypatch.delenv(var, raising=False)


def test_unset_non_production_is_unrestricted(monkeypatch):
    _clear_env(monkeypatch)
    assert allowed_models() is None
    assert model_allowed("anything/at-all")


def test_explicit_allowlist_parsed(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("LLM_ALLOWED_MODELS", "openai/gpt-4o-mini, google/gemini-flash")
    assert allowed_models() == {"openai/gpt-4o-mini", "google/gemini-flash"}
    assert model_allowed("google/gemini-flash")
    assert not model_allowed("openai/o1-pro")


def test_production_unset_falls_back_to_default_model(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "openai/gpt-4o-mini")
    assert allowed_models() == {"openai/gpt-4o-mini"}
    assert model_allowed("openai/gpt-4o-mini")
    assert not model_allowed("openai/o1-pro")


def test_explicit_allowlist_overrides_production_default(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "openai/gpt-4o-mini")
    monkeypatch.setenv("LLM_ALLOWED_MODELS", "anthropic/claude-haiku-4.5")
    assert allowed_models() == {"anthropic/claude-haiku-4.5"}


def test_get_client_drops_disallowed_override(monkeypatch):
    """A stale Prompt row holding a disallowed model must resolve to the default."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "openai/gpt-4o-mini")
    _, model = get_client_for_profile(None, model_override="openai/o1-pro")
    assert model == "openai/gpt-4o-mini"


def test_get_client_keeps_allowed_override(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "openai/gpt-4o-mini")
    monkeypatch.setenv("LLM_ALLOWED_MODELS", "openai/gpt-4o-mini,openai/gpt-4o")
    _, model = get_client_for_profile(None, model_override="openai/gpt-4o")
    assert model == "openai/gpt-4o"
