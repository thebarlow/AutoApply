import pytest
from fastapi import HTTPException

from web.routers import config as config_router


def test_write_env_blocked_in_production(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(config_router, "_ENV_PATH", tmp_path / ".env")
    with pytest.raises(HTTPException) as exc:
        config_router._write_env({"LLM_KEY_OPENAI": "sk-x"})
    assert exc.value.status_code == 400
    assert not (tmp_path / ".env").exists()  # nothing written


def test_write_env_allowed_when_not_production(monkeypatch, tmp_path):
    monkeypatch.delenv("APP_ENV", raising=False)
    env_path = tmp_path / ".env"
    monkeypatch.setattr(config_router, "_ENV_PATH", env_path)
    config_router._write_env({"LLM_KEY_OPENAI": "sk-x"})
    assert "LLM_KEY_OPENAI=sk-x" in env_path.read_text(encoding="utf-8")
