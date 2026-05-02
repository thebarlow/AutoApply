import json
import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.models import Base, Config
from core.llm import LLMProvider, get_active_provider


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
