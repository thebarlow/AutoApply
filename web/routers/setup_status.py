from __future__ import annotations

import json
import os
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db.database import get_db
from core.user import User
from web.routers.config import _get_providers, _read_env, _env_key_name
from web.tenancy import current_profile_id

router = APIRouter()


def _has_configured_llm_provider(db: Session) -> bool:
    """Return True if a usable LLM key is configured.

    On the hosted app the platform owns the key via ``LLM_API_KEY`` (see
    ``core.llm.get_client_for_profile``); that alone makes the LLM usable. Local
    setups may instead carry per-provider or per-profile keys in the env file.
    """
    env = _read_env()
    if os.getenv("LLM_API_KEY") or env.get("LLM_API_KEY"):
        return True
    for p in _get_providers(db):
        if env.get(_env_key_name(p["id"])):
            return True
    for profile in db.query(User).all():
        if env.get(f"LLM_KEY_PROFILE_{profile.id}"):
            return True
    return False


def _has_parsed_resume(db: Session, profile_id: int) -> bool:
    """Return True if the caller's profile has parsed resume content.

    Checks for structured data in skills, work_history, education, or projects.
    Scoped to ``profile_id`` (the tenancy seam) so a new tenant is never judged
    against another tenant's resume.
    """
    row = db.query(User).filter_by(id=profile_id).first()

    if row is None:
        return False

    # Parse profile data
    data = json.loads(row.data) if row.data else {}

    # Check if any structured data exists
    if data.get("skills"):
        return True
    if data.get("work_history"):
        return True
    if data.get("education"):
        return True
    if data.get("projects"):
        return True

    return False


@router.get("/api/setup-status")
def get_setup_status(
    db: Session = Depends(get_db),
    profile_id: int = Depends(current_profile_id),
) -> dict[str, Any]:
    """Return onboarding checklist status.

    Used by the frontend to decide whether to show the first-run wizard
    and to gate Score/Generate/Parse actions.

    Returns:
        {
            "llm_configured": bool,  # At least one provider with a usable API key
            "resume_parsed": bool,   # Active profile has structured resume data
        }
    """
    return {
        "llm_configured": _has_configured_llm_provider(db),
        "resume_parsed": _has_parsed_resume(db, profile_id),
    }
