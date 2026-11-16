"""Bring-your-own-key endpoints: store, inspect, test, and remove an account's LLM key.

The raw key is accepted on write only. Responses carry the provider, a masked
last-four, and the default model — never the key or its ciphertext.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core import byok, secret_box
from core.credits import get_account_for_profile
from db.database import Account, get_db
from web.tenancy import current_profile_id

router = APIRouter(prefix="/api/account/llm-key", tags=["byok"])

logger = logging.getLogger(__name__)


class TestKeyBody(BaseModel):
    provider: str
    api_key: str = Field(min_length=8, max_length=512)


class SaveKeyBody(TestKeyBody):
    default_model: str = Field(min_length=1, max_length=200)


class ModelBody(BaseModel):
    default_model: str = Field(min_length=1, max_length=200)


def _account(db: Session, profile_id: int) -> Account:
    acct = get_account_for_profile(db, profile_id)
    if acct is None:
        # Local/dev installs without auth have no account row; they configure
        # the platform key in .env instead.
        raise HTTPException(status_code=409, detail="No account. Set LLM_API_KEY in .env for local use.")
    return acct


def _state(acct: Account) -> dict:
    stored = byok.has_key(acct)
    return {
        "has_key": stored,
        "provider": acct.llm_provider if stored else None,
        "provider_label": byok.PROVIDERS[acct.llm_provider]["label"] if stored else None,
        "masked_key": byok.mask(acct.llm_key_last4) if stored else "",
        "default_model": acct.llm_default_model if stored else None,
        "storage_available": secret_box.is_available(),
        "providers": [{"id": k, "label": v["label"]} for k, v in byok.PROVIDERS.items()],
    }


def _validate(provider: str, api_key: str) -> list[dict]:
    if provider not in byok.PROVIDERS:
        raise HTTPException(status_code=422, detail="Unsupported provider.")
    try:
        return byok.list_text_models(provider, api_key.strip())
    except byok.KeyValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("")
def get_key_state(db: Session = Depends(get_db),
                  profile_id: int = Depends(current_profile_id)) -> dict:
    return _state(_account(db, profile_id))


@router.post("/test")
def test_key(body: TestKeyBody, db: Session = Depends(get_db),
             profile_id: int = Depends(current_profile_id)) -> dict:
    """Check a key with the provider and return its text models. Nothing is stored."""
    _account(db, profile_id)
    return {"models": _validate(body.provider, body.api_key)}


@router.put("")
def save_key(body: SaveKeyBody, db: Session = Depends(get_db),
             profile_id: int = Depends(current_profile_id)) -> dict:
    acct = _account(db, profile_id)
    if not secret_box.is_available():
        raise HTTPException(status_code=503, detail="Key storage is not configured on this server.")
    key = body.api_key.strip()
    models = _validate(body.provider, key)
    if body.default_model not in {m["id"] for m in models}:
        raise HTTPException(status_code=422, detail="That model isn't available for this key.")
    acct.llm_provider = body.provider
    acct.llm_api_key_enc = secret_box.encrypt(key)
    acct.llm_key_last4 = key[-4:]
    acct.llm_default_model = body.default_model
    db.commit()
    logger.info("BYOK key saved for account %s (provider=%s)", acct.id, body.provider)
    return _state(acct)


@router.get("/models")
def list_models(db: Session = Depends(get_db),
                profile_id: int = Depends(current_profile_id)) -> dict:
    """Text models available to the stored key (for model pickers)."""
    acct = _account(db, profile_id)
    cfg = byok.config_for_account(acct)
    if cfg is None:
        raise HTTPException(status_code=404, detail="No API key saved.")
    try:
        return {"models": byok.list_text_models(cfg.provider, cfg.api_key)}
    except byok.KeyValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("")
def set_default_model(body: ModelBody, db: Session = Depends(get_db),
                      profile_id: int = Depends(current_profile_id)) -> dict:
    acct = _account(db, profile_id)
    if not byok.has_key(acct):
        raise HTTPException(status_code=404, detail="No API key saved.")
    acct.llm_default_model = body.default_model
    db.commit()
    return _state(acct)


@router.delete("")
def delete_key(db: Session = Depends(get_db),
               profile_id: int = Depends(current_profile_id)) -> dict:
    acct = _account(db, profile_id)
    acct.llm_provider = None
    acct.llm_api_key_enc = None
    acct.llm_key_last4 = None
    acct.llm_default_model = None
    db.commit()
    logger.info("BYOK key removed for account %s", acct.id)
    return _state(acct)
