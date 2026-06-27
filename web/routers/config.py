from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import get_db
from db.database import Config, FieldHelp
from core.user import User, PromptNotConfiguredError
from core.profile_tree import (
    FieldNode,
    ListNode,
    RootNode,
    SectionNode,
    TreeValidationError,
    merge_flat_into_stored,
    tree_to_legacy,
    validate_tree,
    validate_tree_limits,
)
from core.job import Job
from core.utils import render_pdf
from core.paths import PROFILES_DIR as _PROFILES_DIR
from core.schemas import ExtraSection, ParseResponse, ParseProposal, ProposedSection
from core.parsed_sections import (
    add_section,
    build_section_from_parsed,
    builtin_sections_from_parse,
    find_section,
    merge_section,
    replace_section,
)
from web.tenancy import current_profile_id

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


# ---- Prompt Templates ----

class PromptBody(BaseModel):
    name: str
    content: str
    provider_name: str = ""
    model_id: str = ""
    template_name: str = ""


class ActivePromptBody(BaseModel):
    active_id: str


def _get_prompts(db: Session, type_: str) -> list[dict]:
    return json.loads(_get(db, f"{type_}_prompts", "[]"))


def _set_prompts(db: Session, type_: str, prompts: list[dict]) -> None:
    _set(db, f"{type_}_prompts", json.dumps(prompts))


def _sync_active_prompt(db: Session, type_: str, active_id: str, prompts: list[dict]) -> None:
    """Keep the legacy template key in sync so the generator always reads current content."""
    legacy_key = f"{type_}_prompt_template"
    match = next((p for p in prompts if p["id"] == active_id), None)
    _set(db, legacy_key, match["content"] if match else "")


@router.get("/api/config/prompts")
def get_all_prompts(db: Session = Depends(get_db)) -> dict[str, Any]:
    all_prompts = []
    for type_ in ("resume", "cover", "description"):
        for p in _get_prompts(db, type_):
            all_prompts.append({
                "id": p["id"],
                "name": p["name"],
                "type": type_,
                "provider_name": p.get("provider_name", ""),
                "model_id": p.get("model_id", ""),
                "template_name": p.get("template_name", ""),
            })
    return {"prompts": all_prompts}


@router.get("/api/config/prompts/active-status")
def get_active_prompt_status(db: Session = Depends(get_db)) -> dict:
    """Return whether each prompt type has a usable active configuration."""
    def _has_latex_template(type_: str) -> bool:
        active_id = _get(db, f"active_{type_}_prompt_id")
        if not active_id:
            return False
        prompts = _get_prompts(db, type_)
        prompt = next((p for p in prompts if p["id"] == active_id), None)
        if not prompt:
            return False
        template_name = prompt.get("template_name", "")
        if not template_name:
            return False
        templates = json.loads(_get(db, "latex_templates", "[]"))
        match = next((t for t in templates if t["name"] == template_name), None)
        if not match:
            return False
        return Path(match["path"]).exists()

    active_desc_id = _get(db, "active_description_prompt_id")
    desc_prompts = _get_prompts(db, "description")
    has_description = bool(active_desc_id and any(p["id"] == active_desc_id for p in desc_prompts))

    return {
        "resume_has_template": _has_latex_template("resume"),
        "cover_has_template": _has_latex_template("cover"),
        "description_has_prompt": has_description,
    }


@router.get("/api/config/prompts/{type_}")
def get_prompts(type_: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    if type_ not in ("resume", "cover", "description"):
        raise HTTPException(status_code=400, detail="type must be resume or cover")
    prompts = _get_prompts(db, type_)
    active_id = _get(db, f"active_{type_}_prompt_id")
    return {"prompts": [{"id": p["id"], "name": p["name"]} for p in prompts], "active_id": active_id}


@router.post("/api/config/prompts/{type_}")
def create_prompt(type_: str, body: PromptBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    if type_ not in ("resume", "cover", "description"):
        raise HTTPException(status_code=400, detail="type must be resume or cover")
    prompts = _get_prompts(db, type_)
    new_id = uuid.uuid4().hex
    prompts.append({
        "id": new_id,
        "name": body.name,
        "content": body.content,
        "provider_name": body.provider_name,
        "model_id": body.model_id,
        "template_name": body.template_name,
    })
    _set_prompts(db, type_, prompts)
    return {"id": new_id, "name": body.name}


# IMPORTANT: /active must be registered before /{prompt_id} to avoid the literal
# string "active" matching the {prompt_id} path parameter.
@router.put("/api/config/prompts/{type_}/active")
def set_active_prompt(type_: str, body: ActivePromptBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    if type_ not in ("resume", "cover", "description"):
        raise HTTPException(status_code=400, detail="type must be resume or cover")
    prompts = _get_prompts(db, type_)
    if not any(p["id"] == body.active_id for p in prompts):
        raise HTTPException(status_code=404, detail="Prompt not found")
    _set(db, f"active_{type_}_prompt_id", body.active_id)
    _sync_active_prompt(db, type_, body.active_id, prompts)
    return {"active_id": body.active_id}


@router.get("/api/config/prompts/{type_}/{prompt_id}")
def get_prompt(type_: str, prompt_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    if type_ not in ("resume", "cover", "description"):
        raise HTTPException(status_code=400, detail="type must be resume or cover")
    prompts = _get_prompts(db, type_)
    match = next((p for p in prompts if p["id"] == prompt_id), None)
    if not match:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return match


@router.put("/api/config/prompts/{type_}/{prompt_id}")
def update_prompt(type_: str, prompt_id: str, body: PromptBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    if type_ not in ("resume", "cover", "description"):
        raise HTTPException(status_code=400, detail="type must be resume or cover")
    prompts = _get_prompts(db, type_)
    match = next((p for p in prompts if p["id"] == prompt_id), None)
    if not match:
        raise HTTPException(status_code=404, detail="Prompt not found")
    match["name"] = body.name
    match["content"] = body.content
    match["provider_name"] = body.provider_name
    match["model_id"] = body.model_id
    match["template_name"] = body.template_name
    _set_prompts(db, type_, prompts)
    active_id = _get(db, f"active_{type_}_prompt_id")
    if active_id == prompt_id:
        _sync_active_prompt(db, type_, prompt_id, prompts)
    return {"id": prompt_id, "name": body.name}


@router.delete("/api/config/prompts/{type_}/{prompt_id}", status_code=204)
def delete_prompt(type_: str, prompt_id: str, db: Session = Depends(get_db)) -> None:
    if type_ not in ("resume", "cover", "description"):
        raise HTTPException(status_code=400, detail="type must be resume or cover")
    prompts = _get_prompts(db, type_)
    remaining = [p for p in prompts if p["id"] != prompt_id]
    if len(remaining) == len(prompts):
        raise HTTPException(status_code=404, detail="Prompt not found")
    _set_prompts(db, type_, remaining)
    active_id = _get(db, f"active_{type_}_prompt_id")
    if active_id == prompt_id:
        _set(db, f"active_{type_}_prompt_id", "")
        _sync_active_prompt(db, type_, "", remaining)


# ---- Templates ----

class TemplatesBody(BaseModel):
    resume_template_path: str = "generator/resume_template.html"
    cover_template_path: str = "generator/cover_template.html"
    resume_prompt_template: str = ""
    cover_prompt_template: str = ""
    github: str = ""
    linkedin: str = ""
    website: str = ""


@router.get("/api/config/templates")
def get_templates(db: Session = Depends(get_db)) -> dict[str, Any]:
    return {
        "resume_template_path": _get(db, "resume_template_path", "generator/resume_template.html"),
        "cover_template_path": _get(db, "cover_template_path", "generator/cover_template.html"),
        "resume_prompt_template": _get(db, "resume_prompt_template", ""),
        "cover_prompt_template": _get(db, "cover_prompt_template", ""),
        "github": _get(db, "resume_github", ""),
        "linkedin": _get(db, "resume_linkedin", ""),
        "website": _get(db, "resume_website", ""),
    }


@router.put("/api/config/templates")
def put_templates(body: TemplatesBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    _set(db, "resume_template_path", body.resume_template_path)
    _set(db, "cover_template_path", body.cover_template_path)
    _set(db, "resume_prompt_template", body.resume_prompt_template)
    _set(db, "cover_prompt_template", body.cover_prompt_template)
    _set(db, "resume_github", body.github)
    _set(db, "resume_linkedin", body.linkedin)
    _set(db, "resume_website", body.website)
    return get_templates(db)


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
    for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            result[k.strip()] = v.strip()
    return result


def _write_env(env: dict[str, str]) -> None:
    # In hosted mode the filesystem is ephemeral and secrets come from the
    # platform's environment, so runtime .env writes are disabled.
    if os.getenv("APP_ENV") == "production":
        raise HTTPException(
            status_code=400,
            detail="API keys are managed via environment variables in hosted mode.",
        )
    lines = [f"{k}={v}" for k, v in env.items()]
    _ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _validate_api_key(key: str) -> str:
    if "\n" in key or "\r" in key:
        raise HTTPException(status_code=422, detail="Invalid api_key format")
    return key


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
            env[f"LLM_KEY_{name.upper()}"] = _validate_api_key(p.api_key)
        to_store.append({"name": name, "base_url": base_url, "model": p.model})
    _write_env(env)
    _set(db, "llm_providers", json.dumps(to_store))
    _set(db, "llm_active_provider", body.active)
    return get_llm(db)


# ---- Named Providers ----

_VALID_PROVIDER_TYPES = {"openrouter", "anthropic", "openai", "gemini"}


class ProviderIn(BaseModel):
    name: str
    provider_type: str
    default_model: str = ""
    api_key: str = ""


def _get_providers(db: Session) -> list[dict]:
    return json.loads(_get(db, "named_providers", "[]"))


def _set_providers(db: Session, providers: list[dict]) -> None:
    _set(db, "named_providers", json.dumps(providers))


def _env_key_name(provider_id: str) -> str:
    return f"LLM_KEY_{provider_id.upper().replace('-', '_')}"


def _mask_key(key: str) -> str:
    if not key:
        return ""
    visible = min(8, len(key))
    return key[:visible] + "•" * max(0, len(key) - visible)


@router.get("/api/config/providers")
def get_providers(db: Session = Depends(get_db)) -> dict[str, Any]:
    providers = _get_providers(db)
    env = _read_env()
    result = []
    for p in providers:
        raw_key = env.get(_env_key_name(p["id"]), "")
        result.append({
            "id": p["id"],
            "name": p["name"],
            "provider_type": p["provider_type"],
            "default_model": p.get("default_model", ""),
            "has_key": bool(raw_key),
            "masked_key": _mask_key(raw_key),
        })
    return {"providers": result}


@router.post("/api/config/providers")
def create_provider(body: ProviderIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    if body.provider_type not in _VALID_PROVIDER_TYPES:
        raise HTTPException(status_code=422, detail=f"Unknown provider_type: {body.provider_type}")
    providers = _get_providers(db)
    new_id = uuid.uuid4().hex
    providers.append({"id": new_id, "name": body.name, "provider_type": body.provider_type, "default_model": body.default_model})
    _set_providers(db, providers)
    if body.api_key:
        env = _read_env()
        env[_env_key_name(new_id)] = _validate_api_key(body.api_key)
        _write_env(env)
    return {"id": new_id, "name": body.name, "provider_type": body.provider_type}


@router.put("/api/config/providers/{provider_id}")
def update_provider(provider_id: str, body: ProviderIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    if body.provider_type not in _VALID_PROVIDER_TYPES:
        raise HTTPException(status_code=422, detail=f"Unknown provider_type: {body.provider_type}")
    providers = _get_providers(db)
    match = next((p for p in providers if p["id"] == provider_id), None)
    if not match:
        raise HTTPException(status_code=404, detail="Provider not found")
    match["name"] = body.name
    match["provider_type"] = body.provider_type
    match["default_model"] = body.default_model
    _set_providers(db, providers)
    env = _read_env()
    if body.api_key:
        env[_env_key_name(provider_id)] = _validate_api_key(body.api_key)
    else:
        env.pop(_env_key_name(provider_id), None)
    _write_env(env)
    return {"id": provider_id, "name": body.name, "provider_type": body.provider_type}


@router.delete("/api/config/providers/{provider_id}", status_code=204)
def delete_provider(provider_id: str, db: Session = Depends(get_db)) -> None:
    providers = _get_providers(db)
    remaining = [p for p in providers if p["id"] != provider_id]
    if len(remaining) == len(providers):
        raise HTTPException(status_code=404, detail="Provider not found")
    _set_providers(db, remaining)
    env = _read_env()
    env.pop(_env_key_name(provider_id), None)
    _write_env(env)


# ---- LaTeX Templates ----

_TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"


class LatexTemplateNameBody(BaseModel):
    name: str


def _get_latex_templates(db: Session) -> list[dict]:
    return json.loads(_get(db, "latex_templates", "[]"))


def _set_latex_templates(db: Session, templates: list[dict]) -> None:
    _set(db, "latex_templates", json.dumps(templates))


@router.get("/api/config/latex-templates")
def get_latex_templates(db: Session = Depends(get_db)) -> dict[str, Any]:
    return {"templates": _get_latex_templates(db)}


@router.post("/api/config/latex-templates")
def create_latex_template(
    name: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    contents = file.file.read()
    if len(contents) > 2 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 2 MB)")
    filename = file.filename or ""
    suffix = Path(filename).suffix.lower()
    if suffix not in (".tex", ".html"):
        raise HTTPException(status_code=400, detail="Only .tex and .html files are accepted")
    _TEMPLATES_DIR.mkdir(exist_ok=True)
    new_id = uuid.uuid4().hex
    dest = _TEMPLATES_DIR / f"{new_id}{suffix}"
    dest.write_bytes(contents)
    try:
        templates = _get_latex_templates(db)
        templates.append({"id": new_id, "name": name, "path": str(dest.resolve())})
        _set_latex_templates(db, templates)
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    return {"id": new_id, "name": name, "path": str(dest.resolve())}


@router.put("/api/config/latex-templates/{template_id}")
def update_latex_template(
    template_id: str,
    body: LatexTemplateNameBody,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    templates = _get_latex_templates(db)
    match = next((t for t in templates if t["id"] == template_id), None)
    if not match:
        raise HTTPException(status_code=404, detail="Template not found")
    match["name"] = body.name
    _set_latex_templates(db, templates)
    return match


@router.delete("/api/config/latex-templates/{template_id}", status_code=204)
def delete_latex_template(template_id: str, db: Session = Depends(get_db)) -> None:
    templates = _get_latex_templates(db)
    match = next((t for t in templates if t["id"] == template_id), None)
    if not match:
        raise HTTPException(status_code=404, detail="Template not found")
    remaining = [t for t in templates if t["id"] != template_id]
    _set_latex_templates(db, remaining)
    path = Path(match.get("path", ""))
    if path.exists():
        path.unlink(missing_ok=True)


# ---- User Profiles ----

_EMPTY_PROFILE_DATA: dict[str, Any] = {
    "email": "", "phone": "", "location": "", "skills": [],
    "work_history": [], "education": [], "target_salary_min": None,
    "target_salary_max": None, "target_roles": [], "resume_path": "",
    "md_path": "", "cover_letter_path": "",
    "resume_uploaded_at": "", "cover_uploaded_at": "",
    "resume_filename": "", "cover_filename": "",
    "resume_max_pages": 1,
}


class ProfileNameBody(BaseModel):
    name: str


class ProfileBody(BaseModel):
    name: str
    data: dict
    llm_api_key: str = ""


class ActiveProfileBody(BaseModel):
    active_id: int


@router.get("/api/config/profiles")
def get_profiles(
    db: Session = Depends(get_db),
    profile_id: int = Depends(current_profile_id),
) -> dict[str, Any]:
    # Scoped to the caller's tenant: 1 account = 1 profile. Never list other
    # tenants' profiles.
    rows = db.query(User).filter_by(id=profile_id).all()
    active_id = profile_id
    profiles = []
    for r in rows:
        data = json.loads(r.data) if r.data else {}
        profiles.append({
            "id": r.id,
            "name": r.name,
            "first_name": data.get("first_name", ""),
            "last_name": data.get("last_name", ""),
            "has_resume": bool(data.get("resume_path") or data.get("md_path")),
            "has_cover": bool(data.get("cover_letter_path")),
            "resume_path": data.get("resume_path", ""),
            "cover_letter_path": data.get("cover_letter_path", ""),
            "resume_uploaded_at": data.get("resume_uploaded_at", ""),
            "cover_uploaded_at": data.get("cover_uploaded_at", ""),
            "resume_filename": data.get("resume_filename", ""),
            "cover_filename": data.get("cover_filename", ""),
        })
    return {"profiles": profiles, "active_id": active_id}


@router.post("/api/config/profiles")
def create_profile(body: ProfileNameBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    row = User(name=body.name, data=json.dumps(_EMPTY_PROFILE_DATA))
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "name": row.name, "data": _EMPTY_PROFILE_DATA}


# IMPORTANT: /active must be registered before /{profile_id} so FastAPI does not
# attempt to coerce the literal string "active" to an integer profile_id.
@router.put("/api/config/profiles/active")
def set_active_profile(body: ActiveProfileBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    row = db.query(User).filter_by(id=body.active_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Profile not found")
    _set(db, "dev_tenant_id", str(body.active_id))
    return {"active_id": body.active_id}


_PROFILE_PROMPT_TYPES = ("scoring", "resume", "cover", "extraction", "resume_parse")


# IMPORTANT: /active/prompt-status must be registered before /{profile_id}.
def _prompt_row_configured(p) -> bool:
    """A prompt slot is 'configured' when its content exceeds the minimum word count."""
    return bool(p and len(p.content.split()) > User._MIN_PROMPT_WORDS)


@router.get("/api/config/profiles/active/prompt-status")
def get_active_profile_prompt_status(
    db: Session = Depends(get_db),
    profile_id: int = Depends(current_profile_id),
) -> dict:
    """Return {type_key: configured_bool} for the caller's profile's prompts.

    Returns all False if the profile row is missing.
    """
    row = db.query(User).filter_by(id=profile_id).first()
    if row is None:
        return {t: False for t in _PROFILE_PROMPT_TYPES}
    from db.database import Prompt
    status = {}
    for t in _PROFILE_PROMPT_TYPES:
        p = db.query(Prompt).filter_by(profile_id=row.id, type_key=t).first()
        status[t] = _prompt_row_configured(p)
    return status


@router.get("/api/config/profiles/{profile_id}")
def get_profile(
    profile_id: int,
    db: Session = Depends(get_db),
    caller_id: int = Depends(current_profile_id),
) -> dict[str, Any]:
    if profile_id != caller_id:
        raise HTTPException(status_code=404, detail="Profile not found")
    row = db.query(User).filter_by(id=profile_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Profile not found")
    data = json.loads(row.data) if row.data else {}
    env = _read_env()
    has_llm_key = bool(env.get(f"LLM_KEY_PROFILE_{profile_id}"))
    from db.database import Prompt
    prompt_types = ("scoring", "resume", "cover", "extraction", "resume_parse")
    prompt_fields = {}
    for t in prompt_types:
        p = db.query(Prompt).filter_by(profile_id=profile_id, type_key=t).first()
        prompt_fields[f"prompt_{t}_model"] = p.model if p else ""
        prompt_fields[f"prompt_{t}_configured"] = _prompt_row_configured(p)
    return {
        "id": row.id,
        "name": row.name,
        "data": data,
        "llm_provider_type": data.get("llm_provider_type", ""),
        "llm_model": data.get("llm_model", ""),
        "has_llm_key": has_llm_key,
        **prompt_fields,
    }


@router.put("/api/config/profiles/{profile_id}")
def update_profile(
    profile_id: int,
    body: ProfileBody,
    db: Session = Depends(get_db),
    caller_id: int = Depends(current_profile_id),
) -> dict[str, Any]:
    if profile_id != caller_id:
        raise HTTPException(status_code=404, detail="Profile not found")
    row = db.query(User).filter_by(id=profile_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Profile not found")
    data = body.data
    if not data.get("name"):
        first = data.get("first_name", "")
        last = data.get("last_name", "")
        data["name"] = f"{first} {last}".strip()
    row.name = body.name
    existing = json.loads(row.data) if row.data else {}
    row.data = json.dumps(merge_flat_into_stored(existing, data))
    db.commit()
    if body.llm_api_key:
        _validate_api_key(body.llm_api_key)
        key_val = body.llm_api_key.strip()
        if key_val:
            env = _read_env()
            env[f"LLM_KEY_PROFILE_{profile_id}"] = key_val
            _write_env(env)
    return {"id": row.id, "name": row.name, "data": data}


@router.delete("/api/config/profiles/{profile_id}", status_code=204)
def delete_profile(
    profile_id: int,
    db: Session = Depends(get_db),
    caller_id: int = Depends(current_profile_id),
) -> None:
    """Delete a profile, clear active_profile_id if needed, and remove owned files from profiles/."""
    if profile_id != caller_id:
        raise HTTPException(status_code=404, detail="Profile not found")
    row = db.query(User).filter_by(id=profile_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Profile not found")
    data = json.loads(row.data)
    db.delete(row)
    active_raw = _get(db, "dev_tenant_id")
    if active_raw and int(active_raw) == profile_id:
        cfg = db.query(Config).filter_by(key="dev_tenant_id").first()
        if cfg:
            cfg.value = ""
        else:
            db.add(Config(key="dev_tenant_id", value=""))
    db.commit()
    env = _read_env()
    if env.pop(f"LLM_KEY_PROFILE_{profile_id}", None) is not None:
        _write_env(env)
    for key in ("resume_path", "md_path", "cover_letter_path"):
        path_str = data.get(key, "")
        if not path_str:
            continue
        path = Path(path_str)
        try:
            if path.is_relative_to(_PROFILES_DIR) and path.exists():
                path.unlink()
        except Exception:
            pass


@router.post("/api/config/profiles/{profile_id}/reset", status_code=204)
def reset_profile(
    profile_id: int,
    db: Session = Depends(get_db),
    caller_id: int = Depends(current_profile_id),
) -> None:
    """Clear all résumé-derived profile data and remove uploaded files.

    Keeps the profile row (and its name), jobs, documents, and prompts. Emptying
    ``data`` makes ``_has_parsed_resume`` report False, re-triggering onboarding.
    """
    if profile_id != caller_id:
        raise HTTPException(status_code=404, detail="Profile not found")
    row = db.query(User).filter_by(id=profile_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Profile not found")
    data = json.loads(row.data) if row.data else {}
    row.data = "{}"
    db.commit()
    for key in ("resume_path", "md_path", "cover_letter_path"):
        path_str = data.get(key, "")
        if not path_str:
            continue
        path = Path(path_str)
        try:
            if path.is_relative_to(_PROFILES_DIR) and path.exists():
                path.unlink()
        except Exception:
            pass


class TreeBody(BaseModel):
    tree: dict


@router.get("/api/config/profiles/{profile_id}/tree")
def get_profile_tree(
    profile_id: int,
    db: Session = Depends(get_db),
    caller_id: int = Depends(current_profile_id),
) -> dict[str, Any]:
    if profile_id != caller_id:
        raise HTTPException(status_code=404, detail="Profile not found")
    try:
        user = User.load(db, profile_id=profile_id)
    except RuntimeError:
        raise HTTPException(status_code=404, detail="Profile not found")
    return {"tree": user.profile_tree.model_dump(mode="json")}


@router.put("/api/config/profiles/{profile_id}/tree")
def put_profile_tree(
    profile_id: int,
    body: TreeBody,
    db: Session = Depends(get_db),
    caller_id: int = Depends(current_profile_id),
) -> dict[str, Any]:
    if profile_id != caller_id:
        raise HTTPException(status_code=404, detail="Profile not found")
    row = db.query(User).filter_by(id=profile_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Profile not found")
    try:
        root = RootNode.model_validate(body.tree)
        validate_tree_limits(root)
        validate_tree(root)
    except (ValueError, TreeValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    existing = json.loads(row.data) if row.data else {}
    derived = tree_to_legacy(root)
    merged = {**existing, **derived, "profile_tree": root.model_dump(mode="json")}
    row.data = json.dumps(merged)
    db.commit()
    return {"tree": root.model_dump(mode="json")}


@router.get("/api/config/profiles/{profile_id}/file")
def serve_profile_file(
    profile_id: int,
    type: str = "pdf",
    db: Session = Depends(get_db),
    caller_id: int = Depends(current_profile_id),
) -> FileResponse:
    if profile_id != caller_id:
        raise HTTPException(status_code=404, detail="Profile not found")
    row = db.query(User).filter_by(id=profile_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Profile not found")
    data = json.loads(row.data)
    if type == "pdf":
        file_path = data.get("resume_path", "")
        media_type = "application/pdf"
    elif type == "md":
        file_path = data.get("md_path", "")
        media_type = "text/plain"
    elif type == "cover":
        file_path = data.get("cover_letter_path", "")
        media_type = "application/pdf"
    else:
        raise HTTPException(status_code=400, detail="type must be 'pdf', 'md', or 'cover'")
    if not file_path:
        raise HTTPException(status_code=404, detail="File path not set")
    path = Path(file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")
    return FileResponse(path, media_type=media_type)


@router.post("/api/config/profiles/{profile_id}/parse")
def parse_profile_from_resume(
    profile_id: int,
    db: Session = Depends(get_db),
    caller_id: int = Depends(current_profile_id),
) -> dict[str, Any]:
    """Parse the already-uploaded resume for a profile and merge extracted data back into it."""
    if profile_id != caller_id:
        raise HTTPException(status_code=404, detail="Profile not found")
    row = db.query(User).filter_by(id=profile_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Profile not found")
    data = json.loads(row.data) if row.data else {}
    resume_path = data.get("resume_path") or data.get("md_path")
    if not resume_path:
        raise HTTPException(status_code=400, detail="No resume uploaded for this profile")
    path = Path(resume_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Resume file not found on disk")
    try:
        if path.suffix.lower() == ".pdf":
            parsed = User.from_pdf(path.read_bytes(), db, profile_id=profile_id)
        else:
            # .md, .txt, or any plain-text format: pass content directly to the LLM
            parsed = User.from_markdown(path.read_text(encoding="utf-8", errors="replace"), db, profile_id=profile_id)
    except PromptNotConfiguredError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    merged = {**_EMPTY_PROFILE_DATA, **parsed}
    merged["resume_path"] = data.get("resume_path", "")
    merged["md_path"] = data.get("md_path", "")
    merged["cover_letter_path"] = data.get("cover_letter_path", "")
    merged["resume_uploaded_at"] = data.get("resume_uploaded_at", "")
    merged["cover_uploaded_at"] = data.get("cover_uploaded_at", "")
    merged["resume_filename"] = data.get("resume_filename", "")
    merged["cover_filename"] = data.get("cover_filename", "")
    # Preserve LLM config — the parse step must not overwrite provider/model/base_url
    for _key in ("llm_provider_type", "llm_model", "llm_base_url"):
        if data.get(_key):
            merged[_key] = data[_key]
    name = parsed.get("name") or row.name
    row.name = name
    existing = json.loads(row.data) if row.data else {}
    row.data = json.dumps(merge_flat_into_stored(existing, merged))
    db.commit()
    return {"id": row.id, "name": name}


# ---------------------------------------------------------------------------
# Parse/propose helpers (Task 5)
# ---------------------------------------------------------------------------

def _section_has_data(section: SectionNode) -> bool:
    """Return True if a SectionNode contains any non-empty user data.

    Inspects FieldNode values, ListNode children counts, and nested
    GroupNode children for non-empty fields.

    Args:
        section: The SectionNode to inspect.

    Returns:
        True if at least one child holds a non-empty value.
    """
    for child in section.children:
        child_type = getattr(child, "type", "")
        if child_type == "field":
            v = getattr(child, "value", None)
            if isinstance(v, list) and v:
                return True
            if isinstance(v, str) and v.strip():
                return True
        elif child_type == "list":
            if getattr(child, "children", None):
                return True
        elif child_type == "group":
            for f in getattr(child, "children", []):
                v = getattr(f, "value", None)
                if isinstance(v, str) and v.strip():
                    return True
                if isinstance(v, list) and v:
                    return True
    return False


def _derive_section_kind(section: SectionNode) -> str:
    """Infer a kind string from the shape of a built-in SectionNode.

    Args:
        section: The built-in SectionNode whose kind to derive.

    Returns:
        One of ``"list"``, ``"taglist"``, ``"bullets"``, ``"markdown"``,
        or ``"fields"``.
    """
    for child in section.children:
        child_type = getattr(child, "type", "")
        if child_type == "list":
            return "list"
        if child_type == "field":
            kind = getattr(child, "kind", "")
            if kind in ("taglist", "bullets", "markdown"):
                return kind
        if child_type == "group":
            return "fields"
    return "fields"


def _preview_for_section(section: SectionNode, kind: str) -> dict:
    """Build a small preview dict describing the parsed content.

    Args:
        section: Source SectionNode.
        kind: The derived kind string for ``section``.

    Returns:
        A lightweight dict; shape depends on ``kind``.
    """
    if kind == "list":
        list_node = next(
            (c for c in section.children if getattr(c, "type", "") == "list"), None
        )
        count = len(list_node.children) if list_node else 0
        return {"count": count}
    if kind in ("taglist", "bullets"):
        field = next(
            (c for c in section.children if getattr(c, "type", "") == "field"), None
        )
        items = list(getattr(field, "value", []) or [])
        return {"items": items[:5]}
    if kind == "markdown":
        field = next(
            (c for c in section.children if getattr(c, "type", "") == "field"), None
        )
        text = getattr(field, "value", "") or ""
        return {"chars": len(text)}
    # fields / default
    group = next(
        (c for c in section.children if getattr(c, "type", "") == "group"), None
    )
    labels = [getattr(f, "name", "") for f in getattr(group, "children", [])]
    return {"fields": labels}


def _preview_for_extra(extra: ExtraSection) -> dict:
    """Build a preview dict for a novel ExtraSection.

    Args:
        extra: The ExtraSection from the parse response.

    Returns:
        A lightweight dict; shape depends on ``extra.kind``.
    """
    if extra.kind == "list":
        return {"count": len(extra.entries)}
    if extra.kind in ("taglist", "bullets"):
        return {"items": list(extra.items)[:5]}
    if extra.kind == "markdown":
        return {"chars": len(extra.markdown)}
    # fields
    return {"fields": [f.label for f in extra.fields]}


def _allowed_actions(kind: str) -> list[str]:
    """Return the allowed actions for a given section kind.

    Args:
        kind: Section kind string.

    Returns:
        List of action strings. Mergeable kinds include ``"merge"``.
    """
    base = ["add", "replace", "skip"]
    if kind in {"list", "taglist", "bullets"}:
        base.append("merge")
    return base


@router.post("/api/config/profiles/{profile_id}/parse/propose")
def parse_propose(
    profile_id: int,
    db: Session = Depends(get_db),
    caller_id: int = Depends(current_profile_id),
) -> ParseProposal:
    """Run the résumé parse and return a ParseProposal without persisting anything.

    Mirrors the ownership guards and résumé-path resolution of
    ``parse_profile_from_resume``, but skips the merge/commit step.

    Args:
        profile_id: The profile to parse.
        db: SQLAlchemy session (injected).
        caller_id: The authenticated profile id (injected).

    Returns:
        A ``ParseProposal`` describing proposed actions for each parsed section.

    Raises:
        HTTPException 404: Profile not found or not owned by caller.
        HTTPException 400: No résumé uploaded, or prompt not configured.
        HTTPException 422: Parse failed (LLM or validation error).
    """
    if profile_id != caller_id:
        raise HTTPException(status_code=404, detail="Profile not found")
    row = db.query(User).filter_by(id=profile_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Profile not found")
    data = json.loads(row.data) if row.data else {}
    resume_path = data.get("resume_path") or data.get("md_path")
    if not resume_path:
        raise HTTPException(status_code=400, detail="No resume uploaded for this profile")
    path = Path(resume_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Resume file not found on disk")
    try:
        if path.suffix.lower() == ".pdf":
            raw_dict = User.from_pdf(path.read_bytes(), db, profile_id=profile_id)
        else:
            raw_dict = User.from_markdown(
                path.read_text(encoding="utf-8", errors="replace"), db, profile_id=profile_id
            )
    except PromptNotConfiguredError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    parsed = ParseResponse.model_validate(raw_dict)

    # Load stored tree to check existing state (do NOT mutate it).
    try:
        stored_user = User.load(db, profile_id=profile_id)
        stored_root: RootNode = stored_user.profile_tree
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    # Determine onboarding: no built-in section currently has data.
    builtin_parsed_sections = builtin_sections_from_parse(parsed)
    def _stored_builtin_has_data(role: str) -> bool:
        stored_s = find_section(stored_root, role=role)
        return bool(stored_s and _section_has_data(stored_s))

    is_onboarding = not any(
        _stored_builtin_has_data(s.role)
        for s in builtin_parsed_sections
        if s.role
    )

    rows: list[ProposedSection] = []

    # Built-in sections from parse
    for s in builtin_parsed_sections:
        if not _section_has_data(s):
            continue  # skip empty parsed sections
        kind = _derive_section_kind(s)
        existing_has_data = _stored_builtin_has_data(s.role)
        if is_onboarding:
            default_action = "replace"
        elif existing_has_data:
            default_action = "skip"
        else:
            default_action = "replace"
        rows.append(ProposedSection(
            name=s.name,
            kind=kind,
            origin="builtin",
            builtin_role=s.role or "",
            extra_index=-1,
            matches_existing=True,
            existing_has_data=existing_has_data,
            default_action=default_action,
            allowed_actions=_allowed_actions(kind),
            preview=_preview_for_section(s, kind),
        ))

    # Novel sections
    for i, extra in enumerate(parsed.extra_sections):
        matched = find_section(stored_root, name=extra.name)
        matches_existing = matched is not None
        existing_has_data = bool(matched and _section_has_data(matched))
        if is_onboarding:
            default_action = "add"
        elif existing_has_data:
            default_action = "skip"
        elif matches_existing:
            default_action = "replace"
        else:
            default_action = "add"
        rows.append(ProposedSection(
            name=extra.name,
            kind=extra.kind,
            origin="novel",
            extra_index=i,
            matches_existing=matches_existing,
            existing_has_data=existing_has_data,
            default_action=default_action,
            allowed_actions=_allowed_actions(extra.kind),
            preview=_preview_for_extra(extra),
        ))

    return ParseProposal(
        builtin=parsed.model_copy(update={"extra_sections": []}),
        extra_sections=parsed.extra_sections,
        sections=rows,
        is_onboarding=is_onboarding,
    )


@router.post("/api/config/profiles/{profile_id}/parse/apply")
def parse_apply(
    profile_id: int,
    proposal: ParseProposal,
    db: Session = Depends(get_db),
    caller_id: int = Depends(current_profile_id),
) -> dict[str, Any]:
    """Persist per-section parse decisions (add / replace / merge / skip) into the profile tree.

    Accepts a ``ParseProposal`` where each ``ProposedSection.action`` has been
    chosen by the user (or pre-filled with the default).  Builtin sections are
    rebuilt from ``proposal.builtin``; novel sections are rebuilt from
    ``proposal.extra_sections``.  The mutated ``RootNode`` is validated and
    written back to the profile row using the same serialisation path as the
    tree PUT endpoint.  File-pointer and LLM-config fields are preserved via the
    ``{**existing, ...}`` spread (``tree_to_legacy`` does not emit those keys).

    Args:
        profile_id: The profile to update.
        proposal: Parsed résumé data with per-section action choices.
        db: SQLAlchemy session (injected).
        caller_id: The authenticated profile id (injected).

    Returns:
        ``{"id": int, "name": str, "applied": int}`` where *applied* is the count
        of sections whose action was not ``"skip"`` or empty.

    Raises:
        HTTPException 404: Profile not found, not owned by caller, or tree missing.
        HTTPException 422: Tree validation failed, merge not possible, or
            extra_index out of range.
    """
    if profile_id != caller_id:
        raise HTTPException(status_code=404, detail="Profile not found")
    row = db.query(User).filter_by(id=profile_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Profile not found")

    # Load the stored profile tree.
    try:
        stored_user = User.load(db, profile_id=profile_id)
        root: RootNode = stored_user.profile_tree
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    # Pre-build a role → SectionNode map for all builtin parsed sections.
    builtin_map: dict[str, SectionNode] = {
        s.role: s
        for s in builtin_sections_from_parse(proposal.builtin)
        if s.role
    }

    applied = 0
    for sect_row in proposal.sections:
        action = sect_row.action or ""
        if not action or action == "skip":
            continue

        # Reconstruct the authoritative incoming SectionNode.
        if sect_row.origin == "builtin":
            incoming = builtin_map.get(sect_row.builtin_role)
            if incoming is None:
                continue  # no data for this builtin role; skip silently
        else:
            idx = sect_row.extra_index
            if idx < 0 or idx >= len(proposal.extra_sections):
                raise HTTPException(
                    status_code=422,
                    detail=f"extra_index {idx} is out of range for extra_sections (len={len(proposal.extra_sections)})",
                )
            incoming = build_section_from_parsed(proposal.extra_sections[idx])
            # Honour any user rename carried on the proposal row.
            if sect_row.name and sect_row.name != incoming.name:
                incoming.name = sect_row.name

        if action == "add":
            add_section(root, incoming)
        elif action == "replace":
            existing = find_section(root, name=sect_row.name, role=sect_row.builtin_role or "")
            if existing is not None:
                replace_section(existing, incoming)
            else:
                add_section(root, incoming)
        elif action == "merge":
            existing = find_section(root, name=sect_row.name, role=sect_row.builtin_role or "")
            if existing is not None:
                try:
                    merge_section(existing, incoming)
                except ValueError as exc:
                    raise HTTPException(status_code=422, detail=str(exc))
            else:
                add_section(root, incoming)
        else:
            # Unknown action — treat as skip.
            continue

        applied += 1

    # Validate the mutated tree before persisting.
    try:
        validate_tree_limits(root)
        validate_tree(root)
    except (ValueError, TreeValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # Persist: spread existing data first so file-pointer + LLM-config fields
    # are preserved (tree_to_legacy does not emit those keys, so {**existing, ...}
    # carries them through unchanged).
    existing_data = json.loads(row.data) if row.data else {}
    derived = tree_to_legacy(root)
    merged = {**existing_data, **derived, "profile_tree": root.model_dump(mode="json")}
    row.data = json.dumps(merged)

    # Optionally set row.name from builtin parsed name if currently blank.
    parsed_name = (
        (proposal.builtin.first_name or "") + " " + (proposal.builtin.last_name or "")
    ).strip()
    if parsed_name and not row.name:
        row.name = parsed_name

    db.commit()
    return {"id": row.id, "name": row.name or "", "applied": applied}


@router.post("/api/config/profile/upload")
def upload_profile_file(file: UploadFile = File(...)) -> dict[str, str]:
    """Save an uploaded resume file to the profiles/ directory and return its absolute path."""
    MAX_BYTES = 10 * 1024 * 1024
    contents = file.file.read()
    if len(contents) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB)")
    filename = file.filename or "resume"
    suffix = Path(filename).suffix.lower()
    if suffix not in (".pdf", ".md", ".txt"):
        raise HTTPException(status_code=400, detail="Only .pdf, .md, and .txt files are accepted")
    _PROFILES_DIR.mkdir(exist_ok=True)
    dest = _PROFILES_DIR / f"{uuid.uuid4().hex}{suffix}"
    dest.write_bytes(contents)
    return {"path": str(dest.resolve()), "filename": filename}


# ---- Sources ----

class SourcesBody(BaseModel):
    remotive: bool = False
    remoteok: bool = False


@router.get("/api/config/sources")
def get_sources(db: Session = Depends(get_db)) -> dict[str, Any]:
    remotive = _get(db, "source_remotive", "false") == "true"
    remoteok = _get(db, "source_remoteok", "false") == "true"
    return {"remotive": remotive, "remoteok": remoteok}


@router.put("/api/config/sources")
def put_sources(body: SourcesBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    _set(db, "source_remotive", "true" if body.remotive else "false")
    _set(db, "source_remoteok", "true" if body.remoteok else "false")
    return {"remotive": body.remotive, "remoteok": body.remoteok}


# ---- Search Config ----

class SearchBody(BaseModel):
    keywords_whitelist: list[str] = []
    keywords_blacklist: list[str] = []
    max_jobs_per_source: int = 50


@router.get("/api/config/search")
def get_search(db: Session = Depends(get_db)) -> dict[str, Any]:
    whitelist = json.loads(_get(db, "keywords_whitelist", "[]"))
    blacklist = json.loads(_get(db, "keywords_blacklist", "[]"))
    max_jobs = int(_get(db, "max_jobs_per_source", "50"))
    return {"keywords_whitelist": whitelist, "keywords_blacklist": blacklist, "max_jobs_per_source": max_jobs}


@router.put("/api/config/search")
def put_search(body: SearchBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    _set(db, "keywords_whitelist", json.dumps(body.keywords_whitelist))
    _set(db, "keywords_blacklist", json.dumps(body.keywords_blacklist))
    _set(db, "max_jobs_per_source", str(body.max_jobs_per_source))
    return body.model_dump()


# ---- Job Searches ----

class JobSearchItem(BaseModel):
    id: str
    title: str = ""
    description: str


class JobSearchesBody(BaseModel):
    searches: list[JobSearchItem]


@router.get("/api/config/job_searches")
def get_job_searches(db: Session = Depends(get_db)) -> dict[str, Any]:
    raw = _get(db, "job_searches", "[]")
    return {"searches": json.loads(raw)}


@router.put("/api/config/job_searches")
def put_job_searches(body: JobSearchesBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    _set(db, "job_searches", json.dumps([s.model_dump() for s in body.searches]))
    return body.model_dump()


@router.post("/api/config/profile/parse")
def parse_profile(file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Parse an uploaded PDF or Markdown resume into a profile dict using the active LLM."""
    MAX_BYTES = 10 * 1024 * 1024  # 10 MB
    contents = file.file.read()
    if len(contents) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB)")
    filename = file.filename or ""
    try:
        if filename.lower().endswith(".pdf"):
            return User.from_pdf(contents, db)
        else:
            return User.from_markdown(contents.decode("utf-8", errors="replace"), db)
    except PromptNotConfiguredError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))


# ---- Job Fields ----

@router.get("/api/job-fields")
def get_job_fields(db: Session = Depends(get_db)) -> dict:
    help_rows = db.query(FieldHelp).filter_by(table_name="jobs").all()
    descriptions = {row.column_name: row.description for row in help_rows}
    fields = [
        {"name": f"job.{col.name}", "description": descriptions.get(col.name, "")}
        for col in Job.__table__.columns
    ]
    return {"fields": fields}


_USER_PROFILE_FIELDS = [
    "name", "first_name", "last_name", "hero", "email", "phone", "linkedin",
    "github", "location", "skills", "work_history", "education", "projects",
    "target_salary_min", "target_salary_max", "target_roles",
]


@router.get("/api/user-profile-fields")
def get_user_profile_fields(db: Session = Depends(get_db)) -> dict:
    help_rows = db.query(FieldHelp).filter_by(table_name="user_profile").all()
    descriptions = {row.column_name: row.description for row in help_rows}
    fields = [
        {"name": f"user_profile.{name}", "description": descriptions.get(name, "")}
        for name in _USER_PROFILE_FIELDS
    ]
    fields.insert(0, {
        "name": "user_profile.master_resume",
        "description": "Full resume content loaded from md_path (or reconstructed from profile fields if md_path is not set)",
    })
    return {"fields": fields}


# ---- Export Master Resume ----

_MASTER_TEMPLATE = Path(__file__).parent.parent.parent / "generator" / "master_template.html"


def _build_master_resume_md(user: Any) -> str:
    lines: list[str] = []

    if user.hero:
        lines += ["## Profile", user.hero, ""]

    if user.education:
        lines.append("## Education")
        for edu in user.education:
            gpa_str = f" — GPA: {edu.gpa}" if edu.gpa else ""
            lines.append(
                f"**{edu.degree} {edu.field}** | {edu.institution} | {edu.graduated}{gpa_str}"
            )
            lines.append("")

    if user.work_history:
        lines.append("## Experience")
        for entry in user.work_history:
            end = entry.end or "Present"
            lines.append(f"**{entry.title}** | {entry.company} | {entry.start} – {end}")
            if entry.summary:
                lines += ["", entry.summary]
            lines.append("")

    if user.projects:
        lines.append("## Projects")
        for proj in user.projects:
            tech_str = (
                f"  \n*Technologies: {', '.join(proj.technologies)}*"
                if proj.technologies else ""
            )
            url_str = f"  \n{proj.url}" if proj.url else ""
            lines.append(f"**{proj.name}** — {proj.description}{tech_str}{url_str}")
            lines.append("")

    if user.skills:
        lines += ["## Skills", ", ".join(user.skills), ""]

    return "\n".join(lines)


@router.post("/api/profile/export-master")
def export_master_resume(db: Session = Depends(get_db)) -> Response:
    try:
        user = User.load(db)
    except RuntimeError:
        raise HTTPException(status_code=404, detail="No profile found")

    md_content = _build_master_resume_md(user)
    tmpdir = Path(tempfile.mkdtemp())
    try:
        md_path = tmpdir / "master.md"
        pdf_path = tmpdir / "master_resume.pdf"
        md_path.write_text(md_content, encoding="utf-8")

        meta = {
            "name": f"{user.first_name} {user.last_name}".strip(),
            "email": user.email,
            "phone": user.phone,
            "location": user.location,
            "linkedin": user.linkedin,
            "github": user.github,
            "website": user.website,
        }
        render_pdf(md_path, pdf_path, _MASTER_TEMPLATE, meta=meta)
        pdf_bytes = pdf_path.read_bytes()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=master_resume.pdf"},
    )
