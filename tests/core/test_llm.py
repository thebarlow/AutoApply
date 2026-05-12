import json
import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from unittest.mock import patch, MagicMock

from db.models import Base, Config
from core.llm import LLMProvider, get_active_provider, get_client_for_named_provider


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _seed(db, key, value):
    db.add(Config(key=key, value=value))
    db.commit()


def test_get_active_provider_returns_match(db_session):
    providers = [
        {"name": "openrouter", "base_url": "https://openrouter.ai/api/v1", "model": "anthropic/claude-sonnet-4-6"},
        {"name": "openai", "base_url": "https://api.openai.com/v1", "model": "gpt-4o"},
    ]
    _seed(db_session, "llm_providers", json.dumps(providers))
    _seed(db_session, "llm_active_provider", "openrouter")

    provider = get_active_provider(db_session)
    assert isinstance(provider, LLMProvider)
    assert provider.name == "openrouter"
    assert provider.base_url == "https://openrouter.ai/api/v1"
    assert provider.model == "anthropic/claude-sonnet-4-6"


def test_get_active_provider_raises_when_no_config(db_session):
    with pytest.raises(RuntimeError, match="No active LLM provider"):
        get_active_provider(db_session)


def test_get_active_provider_raises_when_active_not_in_list(db_session):
    providers = [{"name": "openai", "base_url": "https://api.openai.com/v1", "model": "gpt-4o"}]
    _seed(db_session, "llm_providers", json.dumps(providers))
    _seed(db_session, "llm_active_provider", "openrouter")

    with pytest.raises(RuntimeError, match="No active LLM provider"):
        get_active_provider(db_session)


def _seed_named_provider(db, provider_id="abc123", name="MyOR", provider_type="openrouter", default_model="claude/sonnet"):
    import json
    providers = [{"id": provider_id, "name": name, "provider_type": provider_type, "default_model": default_model}]
    db.add(Config(key="named_providers", value=json.dumps(providers)))
    db.commit()


def test_get_client_for_named_provider_returns_client_and_model(db_session):
    _seed_named_provider(db_session)
    with patch.dict(os.environ, {"LLM_KEY_ABC123": "sk-test"}):
        with patch("core.llm.openai") as mock_openai:
            mock_openai.OpenAI.return_value = MagicMock()
            client, model = get_client_for_named_provider(db_session, "MyOR", "custom/model")
    mock_openai.OpenAI.assert_called_once_with(
        api_key="sk-test",
        base_url="https://openrouter.ai/api/v1",
    )
    assert model == "custom/model"


def test_get_client_for_named_provider_uses_default_model_when_model_id_empty(db_session):
    _seed_named_provider(db_session, default_model="default/model")
    with patch.dict(os.environ, {"LLM_KEY_ABC123": "sk-test"}):
        with patch("core.llm.openai") as mock_openai:
            mock_openai.OpenAI.return_value = MagicMock()
            client, model = get_client_for_named_provider(db_session, "MyOR", "")
    assert model == "default/model"


def test_get_client_for_named_provider_raises_when_provider_not_found(db_session):
    with pytest.raises(RuntimeError, match="Provider 'missing'"):
        get_client_for_named_provider(db_session, "missing", "gpt-4o")


def test_get_client_for_named_provider_raises_when_no_api_key(db_session):
    _seed_named_provider(db_session)
    env_without_key = {k: v for k, v in os.environ.items() if k != "LLM_KEY_ABC123"}
    with patch.dict(os.environ, env_without_key, clear=True):
        with pytest.raises(RuntimeError, match="No API key"):
            get_client_for_named_provider(db_session, "MyOR", "model")
