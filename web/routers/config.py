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


# ---- Templates ----

class TemplatesBody(BaseModel):
    resume_template_path: str
    cover_template_path: str
    resume_prompt_template: str
    cover_prompt_template: str
    github: str
    linkedin: str
    website: str


@router.get("/api/config/templates")
def get_templates(db: Session = Depends(get_db)) -> dict[str, str]:
    return {
        "resume_template_path": _get(db, "resume_template_path", "generator/resume_template.tex"),
        "cover_template_path": _get(db, "cover_template_path", "generator/cover_template.tex"),
        "resume_prompt_template": _get(db, "resume_prompt_template"),
        "cover_prompt_template": _get(db, "cover_prompt_template"),
        "github": _get(db, "resume_github"),
        "linkedin": _get(db, "resume_linkedin"),
        "website": _get(db, "resume_website"),
    }


@router.put("/api/config/templates")
def put_templates(body: TemplatesBody, db: Session = Depends(get_db)) -> dict[str, str]:
    _set(db, "resume_template_path", body.resume_template_path)
    _set(db, "cover_template_path", body.cover_template_path)
    _set(db, "resume_prompt_template", body.resume_prompt_template)
    _set(db, "cover_prompt_template", body.cover_prompt_template)
    _set(db, "resume_github", body.github)
    _set(db, "resume_linkedin", body.linkedin)
    _set(db, "resume_website", body.website)
    return body.model_dump()


# ---- Scoring ----

class ScoringBody(BaseModel):
    w1: float
    w2: float
    auto_reject_threshold: float
    auto_approve_threshold: float


@router.get("/api/config/scoring")
def get_scoring(db: Session = Depends(get_db)) -> dict[str, float]:
    return {
        "w1": float(_get(db, "w1", "0.5")),
        "w2": float(_get(db, "w2", "0.5")),
        "auto_reject_threshold": float(_get(db, "auto_reject_threshold", "0.5")),
        "auto_approve_threshold": float(_get(db, "auto_approve_threshold", "0.5")),
    }


@router.put("/api/config/scoring")
def put_scoring(body: ScoringBody, db: Session = Depends(get_db)) -> dict[str, float]:
    if abs(body.w1 + body.w2 - 1.0) > 0.001:
        raise HTTPException(status_code=422, detail="w1 + w2 must equal 1.0")
    if body.auto_reject_threshold >= body.auto_approve_threshold:
        raise HTTPException(
            status_code=422,
            detail="auto_reject_threshold must be less than auto_approve_threshold",
        )
    _set(db, "w1", str(body.w1))
    _set(db, "w2", str(body.w2))
    _set(db, "auto_reject_threshold", str(body.auto_reject_threshold))
    _set(db, "auto_approve_threshold", str(body.auto_approve_threshold))
    return body.model_dump()
