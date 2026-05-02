from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import Config

router = APIRouter()

_ENV_PATH = Path(__file__).parent.parent.parent / ".env"

_LLM_BASE_URLS: dict[str, str] = {
    "openrouter": "https://openrouter.ai/api/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "openai": "https://api.openai.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
}


def _get(db: Session, key: str, default: str = "") -> str:
    row = db.query(Config).filter_by(key=key).first()
    return row.value if row else default


def _set(db: Session, key: str, value: str) -> None:
    row = db.query(Config).filter_by(key=key).first()
    if row:
        row.value = value
    else:
        db.add(Config(key=key, value=value))
    db.commit()


# ---- Sources ----

class SourcesBody(BaseModel):
    remotive: bool
    remoteok: bool


@router.get("/api/config/sources")
def get_sources(db: Session = Depends(get_db)) -> dict[str, bool]:
    raw = _get(db, "scraper_sources")
    enabled = {s.strip() for s in raw.split(",") if s.strip()}
    return {"remotive": "remotive" in enabled, "remoteok": "remoteok" in enabled}


@router.put("/api/config/sources")
def put_sources(body: SourcesBody, db: Session = Depends(get_db)) -> dict[str, bool]:
    ids = [k for k, v in body.model_dump().items() if v]
    _set(db, "scraper_sources", ",".join(ids))
    return body.model_dump()


# ---- Search ----

class SearchBody(BaseModel):
    keywords_whitelist: list[str]
    keywords_blacklist: list[str]
    max_jobs_per_source: int


@router.get("/api/config/search")
def get_search(db: Session = Depends(get_db)) -> dict[str, Any]:
    return {
        "keywords_whitelist": json.loads(_get(db, "keywords_whitelist", "[]")),
        "keywords_blacklist": json.loads(_get(db, "keywords_blacklist", "[]")),
        "max_jobs_per_source": int(_get(db, "max_jobs_per_source", "50")),
    }


@router.put("/api/config/search")
def put_search(body: SearchBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    _set(db, "keywords_whitelist", json.dumps(body.keywords_whitelist))
    _set(db, "keywords_blacklist", json.dumps(body.keywords_blacklist))
    _set(db, "max_jobs_per_source", str(body.max_jobs_per_source))
    return body.model_dump()
