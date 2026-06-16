from unittest.mock import MagicMock, patch

from web.routers import credits as credits_mod


def test_remaining_none_without_key(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    assert credits_mod.openrouter_remaining() is None


def test_remaining_computes_from_api(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "k")
    resp = MagicMock()
    resp.json.return_value = {"data": {"total_credits": 30.0, "total_usage": 12.0}}
    resp.raise_for_status.return_value = None
    with patch("web.routers.credits.httpx.get", return_value=resp):
        assert credits_mod.openrouter_remaining() == 18.0


def test_remaining_none_on_http_error(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "k")
    import httpx
    with patch("web.routers.credits.httpx.get", side_effect=httpx.HTTPError("x")):
        assert credits_mod.openrouter_remaining() is None
