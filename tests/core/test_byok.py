"""BYOK: encryption at rest, metering bypass, client resolution, model filtering."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import core.metering as metering
from core import byok, secret_box
from db.database import Account, Base, CreditLedger


@pytest.fixture(autouse=True)
def _enc_key(monkeypatch):
    monkeypatch.setenv("KEY_ENCRYPTION_KEY", secret_box.generate_key())


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _acct(db, *, key: str | None = "sk-test-abcd1234", balance=0):
    a = Account(email="u@x.c", is_admin=False, profile_id=1, created_at="now",
                credit_balance=balance, credit_rate=1.0)
    if key:
        a.llm_provider = "openai"
        a.llm_api_key_enc = secret_box.encrypt(key)
        a.llm_key_last4 = key[-4:]
        a.llm_default_model = "gpt-4o-mini"
    db.add(a)
    db.commit()
    return a


def test_encrypt_roundtrip_and_ciphertext_hides_key():
    token = secret_box.encrypt("sk-secret-value")
    assert "sk-secret-value" not in token
    assert secret_box.decrypt(token) == "sk-secret-value"


def test_decrypt_with_rotated_key_returns_none(monkeypatch):
    token = secret_box.encrypt("sk-secret-value")
    monkeypatch.setenv("KEY_ENCRYPTION_KEY", secret_box.generate_key())
    assert secret_box.decrypt(token) is None


def test_missing_encryption_key_reports_unavailable(monkeypatch):
    monkeypatch.delenv("KEY_ENCRYPTION_KEY")
    assert not secret_box.is_available()
    with pytest.raises(secret_box.SecretBoxUnavailable):
        secret_box.encrypt("x")


def test_byok_action_is_free_even_with_zero_balance(db_session):
    _acct(db_session, balance=0)
    with metering.meter_action(db_session, 1, action="generate_fresh", job_key="j1"):
        assert byok.active() is not None
        assert byok.active().api_key == "sk-test-abcd1234"
    assert byok.active() is None
    assert db_session.query(CreditLedger).count() == 0


def test_byok_credential_pinned_if_key_deleted_mid_action(db_session):
    acct = _acct(db_session)
    with metering.meter_action(db_session, 1, action="score", job_key="j1"):
        acct.llm_api_key_enc = None
        db_session.commit()
        assert byok.active().api_key == "sk-test-abcd1234"


def test_non_byok_account_still_metered(db_session):
    from core.credits import InsufficientCredits
    _acct(db_session, key=None, balance=0)
    with pytest.raises(InsufficientCredits):
        with metering.meter_action(db_session, 1, action="score", job_key="j1"):
            pass


def test_undecryptable_key_falls_back_to_metering(db_session, monkeypatch):
    from core.credits import InsufficientCredits
    _acct(db_session, balance=0)
    monkeypatch.setenv("KEY_ENCRYPTION_KEY", secret_box.generate_key())
    with pytest.raises(InsufficientCredits):
        with metering.meter_action(db_session, 1, action="score", job_key="j1"):
            pass


def test_client_uses_pinned_byok_key_and_any_model(monkeypatch):
    from core.llm import get_client_for_profile
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("LLM_ALLOWED_MODELS", "only/this-model")
    cfg = byok.ByokConfig("anthropic", "sk-ant-xyz", "claude-sonnet-4-5")
    token = byok.set_active(cfg)
    try:
        client, model = get_client_for_profile(None, "claude-opus-4-1")
    finally:
        byok.reset_active(token)
    assert model == "claude-opus-4-1"  # not clamped to the platform allowlist
    assert client.api_key == "sk-ant-xyz"
    assert str(client.base_url).startswith("https://api.anthropic.com/v1")


def test_client_uses_byok_default_model_when_no_override():
    from core.llm import get_client_for_profile
    token = byok.set_active(byok.ByokConfig("gemini", "g-key", "gemini-2.5-flash"))
    try:
        _, model = get_client_for_profile(None, "")
    finally:
        byok.reset_active(token)
    assert model == "gemini-2.5-flash"


@pytest.mark.parametrize("provider,model,expected", [
    ("openai", {"id": "gpt-4o-mini"}, True),
    ("openai", {"id": "gpt-4o-realtime-preview"}, False),
    ("openai", {"id": "text-embedding-3-small"}, False),
    ("openai", {"id": "dall-e-3"}, False),
    ("openai", {"id": "o3-mini"}, True),
    ("gemini", {"id": "gemini-2.5-pro"}, True),
    ("gemini", {"id": "gemini-embedding-001"}, False),
    ("gemini", {"id": "imagen-3.0-generate-002"}, False),
    ("anthropic", {"id": "claude-sonnet-4-5"}, True),
    ("openrouter", {"id": "a/b", "architecture": {"output_modalities": ["text"]}}, True),
    ("openrouter", {"id": "a/img", "architecture": {"output_modalities": ["image", "text"]}}, False),
])
def test_text_model_filter(provider, model, expected):
    assert byok._is_text_model(provider, model) is expected


def test_list_text_models_rejects_bad_key(monkeypatch):
    import httpx

    def fake_get(url, **kw):
        return httpx.Response(401, json={"error": "bad key"}, request=httpx.Request("GET", url))

    monkeypatch.setattr(byok.httpx, "get", fake_get)
    with pytest.raises(byok.KeyValidationError):
        byok.list_text_models("openai", "sk-bad")
