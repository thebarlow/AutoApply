from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db.database import get_db, Config
from core.user import User
from web.routers.config import _get_providers, _read_env, _env_key_name

router = APIRouter()


def _has_configured_llm_provider(db: Session) -> bool:
    """Return True if any named provider or profile has a usable API key."""
    env = _read_env()
    for p in _get_providers(db):
        if env.get(_env_key_name(p["id"])):
            return True
    for profile in db.query(User).all():
        if env.get(f"LLM_KEY_PROFILE_{profile.id}"):
            return True
    return False


def _has_parsed_resume(db: Session) -> bool:
    """Return True if the active profile has parsed resume content.

    Checks for structured data in skills, work_history, education, or projects.
    """
    # Get active profile (same logic as config.py)
    active_raw = db.query(Config).filter_by(key="active_profile_id").first()
    row: User | None = None

    if active_raw and active_raw.value:
        try:
            row = db.query(User).filter_by(id=int(active_raw.value)).first()
        except (ValueError, TypeError):
            pass

    if row is None:
        row = db.query(User).first()

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
def get_setup_status(db: Session = Depends(get_db)) -> dict[str, Any]:
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
        "resume_parsed": _has_parsed_resume(db),
    }
