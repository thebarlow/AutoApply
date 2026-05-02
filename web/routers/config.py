from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import get_db
import core.profile_parser as _parser
from db.models import Config, UserProfileModel

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


# ---- .env helpers ----

def _read_env() -> dict[str, str]:
    if not _ENV_PATH.exists():
        return {}
    result: dict[str, str] = {}
    for line in _ENV_PATH.read_text().splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            result[k.strip()] = v.strip()
    return result


def _write_env(env: dict[str, str]) -> None:
    lines = [f"{k}={v}" for k, v in env.items()]
    _ENV_PATH.write_text("\n".join(lines) + "\n")


# ---- LLM ----

class LLMProviderIn(BaseModel):
    name: str
    model: str
    api_key: str = ""


class LLMBody(BaseModel):
    providers: list[LLMProviderIn]
    active: str


@router.get("/api/config/llm")
def get_llm(db: Session = Depends(get_db)) -> dict[str, Any]:
    providers = json.loads(_get(db, "llm_providers", "[]"))
    active = _get(db, "llm_active_provider")
    env = _read_env()
    result = [
        {
            "name": p["name"],
            "base_url": p["base_url"],
            "model": p["model"],
            "has_key": bool(env.get(f"LLM_KEY_{p['name'].upper()}")),
        }
        for p in providers
    ]
    return {"providers": result, "active": active}


@router.put("/api/config/llm")
def put_llm(body: LLMBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    env = _read_env()
    to_store = []
    for p in body.providers:
        name = p.name.lower()
        base_url = _LLM_BASE_URLS.get(name)
        if not base_url:
            raise HTTPException(status_code=422, detail=f"Unknown provider: {p.name}")
        if p.api_key:
            env[f"LLM_KEY_{name.upper()}"] = p.api_key
        to_store.append({"name": name, "base_url": base_url, "model": p.model})
    _write_env(env)
    _set(db, "llm_providers", json.dumps(to_store))
    _set(db, "llm_active_provider", body.active)
    return get_llm(db)


# ---- User Profiles ----

_EMPTY_PROFILE_DATA: dict = {
    "email": "", "phone": "", "location": "", "skills": [],
    "work_history": [], "education": [], "target_salary_min": None,
    "target_salary_max": None, "target_roles": [], "resume_path": "",
}


class ProfileNameBody(BaseModel):
    name: str


class ProfileBody(BaseModel):
    name: str
    data: dict


class ActiveProfileBody(BaseModel):
    active_id: int


@router.get("/api/config/profiles")
def get_profiles(db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = db.query(UserProfileModel).all()
    active_raw = _get(db, "active_profile_id")
    active_id = int(active_raw) if active_raw else None
    return {
        "profiles": [{"id": r.id, "name": r.name} for r in rows],
        "active_id": active_id,
    }


@router.post("/api/config/profiles")
def create_profile(body: ProfileNameBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    row = UserProfileModel(name=body.name, data=json.dumps(_EMPTY_PROFILE_DATA))
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "name": row.name, "data": _EMPTY_PROFILE_DATA}


@router.put("/api/config/profiles/active")
def set_active_profile(body: ActiveProfileBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    _set(db, "active_profile_id", str(body.active_id))
    return {"active_id": body.active_id}


@router.get("/api/config/profiles/{profile_id}")
def get_profile(profile_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    row = db.query(UserProfileModel).filter_by(id=profile_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Profile not found")
    return {"id": row.id, "name": row.name, "data": json.loads(row.data)}


@router.put("/api/config/profiles/{profile_id}")
def update_profile(profile_id: int, body: ProfileBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    row = db.query(UserProfileModel).filter_by(id=profile_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Profile not found")
    row.name = body.name
    row.data = json.dumps(body.data)
    db.commit()
    return {"id": row.id, "name": row.name, "data": body.data}


@router.delete("/api/config/profiles/{profile_id}", status_code=204)
def delete_profile(profile_id: int, db: Session = Depends(get_db)) -> None:
    row = db.query(UserProfileModel).filter_by(id=profile_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Profile not found")
    db.delete(row)
    db.commit()


@router.post("/api/config/profile/parse")
async def parse_profile(file: UploadFile = File(...)) -> dict[str, Any]:
    contents = await file.read()
    filename = file.filename or ""
    if filename.lower().endswith(".pdf"):
        md_text = _parser.pdf_to_markdown(contents)
    else:
        md_text = contents.decode("utf-8", errors="replace")
    return _parser.markdown_to_profile(md_text)
