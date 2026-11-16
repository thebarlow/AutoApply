"""BYOK key-management endpoints: the raw key is write-only and never echoed."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import core.user  # noqa: F401
from core import byok, secret_box
from core.user import User
from db.database import Account, Base, get_db
from web.main import app
from web.tenancy import current_profile_id

RAW_KEY = "sk-live-very-secret-9876"
MODELS = [{"id": "gpt-4o-mini", "name": "gpt-4o-mini"}, {"id": "gpt-4.1", "name": "gpt-4.1"}]


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("KEY_ENCRYPTION_KEY", secret_box.generate_key())
    monkeypatch.setattr(byok, "list_text_models", lambda provider, key: list(MODELS))


@pytest.fixture
def db_session():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    Base.metadata.create_all(eng)
    s = sessionmaker(bind=eng)()
    s.add(User(id=1, name="T", data="{}"))
    s.add(Account(email="u@x.c", is_admin=False, profile_id=1, created_at="now",
                  credit_balance=0, credit_rate=1.0))
    s.commit()
    yield s
    s.close()


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[current_profile_id] = lambda: 1
    yield TestClient(app)
    app.dependency_overrides.clear()


def _save(client, model="gpt-4o-mini"):
    return client.put("/api/account/llm-key",
                      json={"provider": "openai", "api_key": RAW_KEY, "default_model": model})


def test_save_stores_encrypted_and_never_echoes_key(client, db_session):
    r = _save(client)
    assert r.status_code == 200, r.text
    assert RAW_KEY not in r.text
    body = r.json()
    assert body["has_key"] and body["masked_key"].endswith("9876")
    acct = db_session.query(Account).first()
    assert acct.llm_api_key_enc and RAW_KEY not in acct.llm_api_key_enc
    assert secret_box.decrypt(acct.llm_api_key_enc) == RAW_KEY
    assert RAW_KEY not in client.get("/api/account/llm-key").text


def test_save_rejects_model_not_offered(client):
    assert _save(client, model="made-up-model").status_code == 422


def test_save_rejects_unknown_provider(client):
    r = client.put("/api/account/llm-key",
                   json={"provider": "acme", "api_key": RAW_KEY, "default_model": "x"})
    assert r.status_code == 422


def test_save_refuses_without_encryption_key(client, monkeypatch):
    monkeypatch.delenv("KEY_ENCRYPTION_KEY")
    assert _save(client).status_code == 503


def test_bad_key_reports_provider_message(client, monkeypatch):
    def reject(provider, key):
        raise byok.KeyValidationError("OpenAI rejected this key.")
    monkeypatch.setattr(byok, "list_text_models", reject)
    r = client.post("/api/account/llm-key/test", json={"provider": "openai", "api_key": RAW_KEY})
    assert r.status_code == 422 and "rejected" in r.json()["detail"]


def test_delete_clears_everything(client, db_session):
    _save(client)
    r = client.delete("/api/account/llm-key")
    assert r.status_code == 200 and r.json()["has_key"] is False
    acct = db_session.query(Account).first()
    assert acct.llm_api_key_enc is None and acct.llm_provider is None


def test_byok_user_may_set_any_prompt_model(client, monkeypatch):
    # Explicit allowlist applies in every env (APP_ENV=production would also
    # engage the auth gate, which this unit test bypasses via overrides).
    monkeypatch.setenv("LLM_ALLOWED_MODELS", "platform/only")
    body = {"content": "word " * 50, "model": "gpt-4.1"}
    assert client.put("/api/prompts/1/scoring", json=body).status_code == 422
    _save(client)
    assert client.put("/api/prompts/1/scoring", json=body).status_code == 200
