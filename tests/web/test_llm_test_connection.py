from unittest.mock import patch
from fastapi.testclient import TestClient
from web.main import app

client = TestClient(app)


def test_test_connection_ok():
    with patch("web.routers.llm_test._ping_provider", return_value=(True, None)):
        r = client.post("/api/llm/test-connection", json={
            "provider_type": "anthropic",
            "api_key": "sk-test",
            "model": "claude-haiku-4-5-20251001",
        })
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_test_connection_failure():
    with patch("web.routers.llm_test._ping_provider", return_value=(False, "bad key")):
        r = client.post("/api/llm/test-connection", json={
            "provider_type": "anthropic",
            "api_key": "bad",
            "model": "claude-haiku-4-5-20251001",
        })
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "bad key" in body.get("error", "")
