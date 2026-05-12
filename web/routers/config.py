from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import get_db
import core.profile_parser as _parser
from db.models import Config, UserProfileModel, Job, FieldHelp

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
    github: str
    linkedin: str
    website: str
    resume_prompt_template: str = ""
    cover_prompt_template: str = ""
    primary_skills: list[str] = []
    primary_technologies: list[str] = []


@router.get("/api/config/templates")
def get_templates(db: Session = Depends(get_db)) -> dict:
    def _get_json_list(key: str) -> list[str]:
        raw = _get(db, key)
        try:
            val = json.loads(raw)
            return val if isinstance(val, list) else []
        except (ValueError, TypeError):
            return []

    return {
        "resume_template_path": _get(db, "resume_template_path", "generator/resume_template.tex"),
        "cover_template_path": _get(db, "cover_template_path", "generator/cover_template.tex"),
        "resume_prompt_template": _get(db, "resume_prompt_template"),
        "cover_prompt_template": _get(db, "cover_prompt_template"),
        "github": _get(db, "resume_github"),
        "linkedin": _get(db, "resume_linkedin"),
        "website": _get(db, "resume_website"),
        "primary_skills": _get_json_list("primary_skills"),
        "primary_technologies": _get_json_list("primary_technologies"),
    }


@router.put("/api/config/templates")
def put_templates(body: TemplatesBody, db: Session = Depends(get_db)) -> dict:
    _set(db, "resume_template_path", body.resume_template_path)
    _set(db, "cover_template_path", body.cover_template_path)
    _set(db, "resume_github", body.github)
    _set(db, "resume_linkedin", body.linkedin)
    _set(db, "resume_website", body.website)
    _set(db, "resume_prompt_template", body.resume_prompt_template)
    _set(db, "cover_prompt_template", body.cover_prompt_template)
    _set(db, "primary_skills", json.dumps(body.primary_skills))
    _set(db, "primary_technologies", json.dumps(body.primary_technologies))
    return body.model_dump()


# ---- Prompt Templates ----

class PromptBody(BaseModel):
    name: str
    content: str


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
    prompts.append({"id": new_id, "name": body.name, "content": body.content})
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


# ---- Named Providers ----

_VALID_PROVIDER_TYPES = {"openrouter", "anthropic", "openai", "gemini"}


class ProviderIn(BaseModel):
    name: str
    provider_type: str
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
    providers.append({"id": new_id, "name": body.name, "provider_type": body.provider_type})
    _set_providers(db, providers)
    if body.api_key:
        env = _read_env()
        env[_env_key_name(new_id)] = body.api_key
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
    _set_providers(db, providers)
    env = _read_env()
    if body.api_key:
        env[_env_key_name(provider_id)] = body.api_key
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


# ---- User Profiles ----

_EMPTY_PROFILE_DATA: dict[str, Any] = {
    "email": "", "phone": "", "location": "", "skills": [],
    "work_history": [], "education": [], "target_salary_min": None,
    "target_salary_max": None, "target_roles": [], "resume_path": "",
    "md_path": "", "cover_letter_path": "",
    "resume_uploaded_at": "", "cover_uploaded_at": "",
    "resume_filename": "", "cover_filename": "",
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
    profiles = []
    for r in rows:
        data = json.loads(r.data) if r.data else {}
        profiles.append({
            "id": r.id,
            "name": r.name,
            "has_resume": bool(data.get("resume_path")),
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
    row = UserProfileModel(name=body.name, data=json.dumps(_EMPTY_PROFILE_DATA))
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "name": row.name, "data": _EMPTY_PROFILE_DATA}


# IMPORTANT: /active must be registered before /{profile_id} so FastAPI does not
# attempt to coerce the literal string "active" to an integer profile_id.
@router.put("/api/config/profiles/active")
def set_active_profile(body: ActiveProfileBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    row = db.query(UserProfileModel).filter_by(id=body.active_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Profile not found")
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
    """Delete a profile and clear active_profile_id if it pointed to this profile."""
    row = db.query(UserProfileModel).filter_by(id=profile_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Profile not found")
    db.delete(row)
    active_raw = _get(db, "active_profile_id")
    if active_raw and int(active_raw) == profile_id:
        cfg = db.query(Config).filter_by(key="active_profile_id").first()
        if cfg:
            cfg.value = ""
        else:
            db.add(Config(key="active_profile_id", value=""))
    db.commit()


@router.get("/api/config/profiles/{profile_id}/file")
def serve_profile_file(
    profile_id: int,
    type: str = "pdf",
    db: Session = Depends(get_db),
) -> FileResponse:
    row = db.query(UserProfileModel).filter_by(id=profile_id).first()
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
def parse_profile_from_resume(profile_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Parse the already-uploaded resume for a profile and merge extracted data back into it."""
    row = db.query(UserProfileModel).filter_by(id=profile_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Profile not found")
    data = json.loads(row.data) if row.data else {}
    resume_path = data.get("resume_path") or data.get("md_path")
    if not resume_path:
        raise HTTPException(status_code=400, detail="No resume uploaded for this profile")
    path = Path(resume_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Resume file not found on disk")
    if path.suffix.lower() == ".pdf":
        md_text = _parser.pdf_to_markdown(path.read_bytes())
    else:
        md_text = path.read_text(errors="replace")
    try:
        parsed = _parser.markdown_to_profile(md_text, db)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    merged = {**_EMPTY_PROFILE_DATA, **parsed}
    merged["resume_path"] = data.get("resume_path", "")
    merged["md_path"] = data.get("md_path", "")
    merged["cover_letter_path"] = data.get("cover_letter_path", "")
    merged["resume_uploaded_at"] = data.get("resume_uploaded_at", "")
    merged["cover_uploaded_at"] = data.get("cover_uploaded_at", "")
    merged["resume_filename"] = data.get("resume_filename", "")
    merged["cover_filename"] = data.get("cover_filename", "")
    name = parsed.get("name") or row.name
    row.name = name
    row.data = json.dumps(merged)
    db.commit()
    return {"id": row.id, "name": name}


_PROFILES_DIR = Path(__file__).parent.parent.parent / "profiles"


@router.post("/api/config/profile/upload")
def upload_profile_file(file: UploadFile = File(...)) -> dict[str, str]:
    """Save an uploaded resume file to the profiles/ directory and return its absolute path."""
    MAX_BYTES = 10 * 1024 * 1024
    contents = file.file.read()
    if len(contents) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB)")
    filename = file.filename or "resume"
    suffix = Path(filename).suffix.lower()
    if suffix not in (".pdf", ".md"):
        raise HTTPException(status_code=400, detail="Only .pdf and .md files are accepted")
    _PROFILES_DIR.mkdir(exist_ok=True)
    dest = _PROFILES_DIR / f"{uuid.uuid4().hex}{suffix}"
    dest.write_bytes(contents)
    return {"path": str(dest.resolve()), "filename": filename}


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
    if filename.lower().endswith(".pdf"):
        md_text = _parser.pdf_to_markdown(contents)
    else:
        md_text = contents.decode("utf-8", errors="replace")
    try:
        return _parser.markdown_to_profile(md_text, db)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))


# ---- Job Fields ----

@router.get("/api/job-fields")
def get_job_fields(db: Session = Depends(get_db)) -> dict:
    help_rows = db.query(FieldHelp).filter_by(table_name="jobs").all()
    descriptions = {row.column_name: row.description for row in help_rows}
    fields = [
        {"name": col.name, "description": descriptions.get(col.name, "")}
        for col in Job.__table__.columns
    ]
    return {"fields": fields}
