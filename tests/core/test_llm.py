import os
from unittest import mock
from unittest.mock import MagicMock

import pytest

from core.llm import call_llm, get_client_for_profile


def test_get_client_for_profile_resolves_from_env():
    env = {
        "LLM_PROVIDER_TYPE": "openai",
        "LLM_API_KEY": "sk-test",
        "LLM_DEFAULT_MODEL": "gpt-4o",
    }
    with mock.patch.dict(os.environ, env, clear=False):
        client, model = get_client_for_profile(None)
    assert model == "gpt-4o"
    assert str(client.base_url).rstrip("/") == "https://api.openai.com/v1"


def test_model_override_beats_env_default():
    env = {"LLM_PROVIDER_TYPE": "openai", "LLM_API_KEY": "sk-test", "LLM_DEFAULT_MODEL": "gpt-4o"}
    with mock.patch.dict(os.environ, env, clear=False):
        _, model = get_client_for_profile(None, "o3-mini")
    assert model == "o3-mini"


def test_missing_api_key_raises():
    env = {"LLM_PROVIDER_TYPE": "openai", "LLM_DEFAULT_MODEL": "gpt-4o", "LLM_API_KEY": ""}
    with mock.patch.dict(os.environ, env, clear=True):
        with mock.patch("core.llm._read_env_file", return_value={}):
            with pytest.raises(RuntimeError, match="LLM_API_KEY"):
                get_client_for_profile(None)


def test_unknown_provider_type_raises():
    env = {"LLM_PROVIDER_TYPE": "bogus", "LLM_API_KEY": "sk-test", "LLM_DEFAULT_MODEL": "m"}
    with mock.patch.dict(os.environ, env, clear=False):
        with pytest.raises(RuntimeError, match="LLM_PROVIDER_TYPE"):
            get_client_for_profile(None)


# --- call_llm tests ---

def _mock_client(content: str):
    client = MagicMock()
    client.chat.completions.create.return_value.choices[0].message.content = content
    client.chat.completions.create.return_value.choices[0].finish_reason = "stop"
    client.chat.completions.create.return_value.usage = None
    return client


def test_call_llm_returns_stripped_content():
    result = call_llm("hello", _mock_client("  world  "), "gpt-4")
    assert result == "world"


def test_call_llm_raises_on_empty_response():
    with pytest.raises(RuntimeError, match="empty response"):
        call_llm("hello", _mock_client(""), "gpt-4")


def test_call_llm_passes_max_tokens():
    client = _mock_client("ok")
    call_llm("prompt", client, "gpt-4", max_tokens=256)
    call_args = client.chat.completions.create.call_args
    assert call_args.kwargs["max_tokens"] == 256
