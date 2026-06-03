from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import Prompt, PromptDefault, get_db
from core.user import User
from db.seed import PROMPT_TYPE_KEYS

router = APIRouter(prefix="/api/prompts")

_VALID_KEYS = set(PROMPT_TYPE_KEYS)


def _require_type(type_key: str) -> None:
    """Raise 404 if type_key is not a recognised prompt type."""
    if type_key not in _VALID_KEYS:
        raise HTTPException(status_code=404, detail="Unknown prompt type")


def _require_profile(profile_id: int, db: Session) -> None:
    """Raise 404 if no User row exists for the given profile_id."""
    if not db.query(User).filter_by(id=profile_id).first():
        raise HTTPException(status_code=404, detail="Profile not found")


def _default_content(type_key: str, db: Session) -> str:
    """Return the default prompt content for type_key, or "" if none exists."""
    d = db.query(PromptDefault).filter_by(type_key=type_key).first()
    return d.content if d else ""


def _slot(profile_id: int, type_key: str, db: Session) -> dict:
    """Return {content, model, is_default} for a slot, falling back to the default when no row exists."""
    row = db.query(Prompt).filter_by(profile_id=profile_id, type_key=type_key).first()
    default = _default_content(type_key, db)
    content = row.content if row is not None else default
    return {
        "content": content,
        "model": row.model if row else "",
        "is_default": bool(default) and content == default,
    }


class PromptBody(BaseModel):
    content: str
    model: str = ""


@router.get("/defaults/{type_key}")
def get_default_prompt(type_key: str, db: Session = Depends(get_db)) -> dict:
    _require_type(type_key)
    content = _default_content(type_key, db)
    if not content:
        raise HTTPException(status_code=404, detail="Default prompt not found")
    return {"content": content}


@router.get("/{profile_id}/{type_key}")
def get_prompt(profile_id: int, type_key: str, db: Session = Depends(get_db)) -> dict:
    _require_type(type_key)
    _require_profile(profile_id, db)
    return _slot(profile_id, type_key, db)


@router.put("/{profile_id}/{type_key}")
def put_prompt(profile_id: int, type_key: str, body: PromptBody, db: Session = Depends(get_db)) -> dict:
    _require_type(type_key)
    _require_profile(profile_id, db)
    if not body.content.strip():
        raise HTTPException(status_code=400, detail="Prompt content cannot be empty")
    now = datetime.now(timezone.utc).isoformat()
    row = db.query(Prompt).filter_by(profile_id=profile_id, type_key=type_key).first()
    if row is None:
        row = Prompt(profile_id=profile_id, type_key=type_key, content=body.content, model=body.model, updated_at=now)
        db.add(row)
    else:
        row.content = body.content
        row.model = body.model
        row.updated_at = now
    db.commit()
    return _slot(profile_id, type_key, db)


@router.post("/{profile_id}/{type_key}/reset")
def reset_prompt(profile_id: int, type_key: str, db: Session = Depends(get_db)) -> dict:
    _require_type(type_key)
    _require_profile(profile_id, db)
    default = _default_content(type_key, db)
    if not default:
        raise HTTPException(status_code=404, detail="Default prompt not found")
    now = datetime.now(timezone.utc).isoformat()
    row = db.query(Prompt).filter_by(profile_id=profile_id, type_key=type_key).first()
    if row is None:
        db.add(Prompt(profile_id=profile_id, type_key=type_key, content=default, model="", updated_at=now))
    else:
        row.content = default
        row.model = ""
        row.updated_at = now
    db.commit()
    return _slot(profile_id, type_key, db)
