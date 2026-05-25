from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/prompts")

_PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"


def _prompt_meta(p: Path) -> dict:
    return {
        "name": p.name,
        "path": str(p),
        "last_modified": p.stat().st_mtime,
    }


_DEFAULTS_DIR = _PROMPTS_DIR / "defaults"

_VALID_DEFAULT_KEYS = {"scoring", "resume", "cover", "extraction", "resume_parse"}


@router.get("/defaults/{type_key}")
def get_default_prompt(type_key: str) -> dict:
    """Return the path and content of a default prompt file."""
    if type_key not in _VALID_DEFAULT_KEYS:
        raise HTTPException(status_code=404, detail="Unknown prompt type")
    p = (_DEFAULTS_DIR / f"{type_key}.md").resolve()
    if not p.exists():
        raise HTTPException(status_code=404, detail="Default prompt file not found")
    return {"path": str(p), "content": p.read_text(encoding="utf-8")}


@router.get("")
def list_prompts() -> dict:
    """List all .md files in the prompts/ directory."""
    _PROMPTS_DIR.mkdir(exist_ok=True)
    files = sorted(_PROMPTS_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    return {"prompts": [_prompt_meta(f) for f in files]}


@router.post("/upload")
def upload_prompt(file: UploadFile = File(...)) -> dict:
    """Save an uploaded .md file to prompts/ and return its metadata."""
    MAX_BYTES = 1 * 1024 * 1024  # 1 MB
    contents = file.file.read()
    if len(contents) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 1 MB)")
    filename = file.filename or "prompt.md"
    if not filename.lower().endswith(".md"):
        raise HTTPException(status_code=400, detail="Only .md files are accepted")
    _PROMPTS_DIR.mkdir(exist_ok=True)
    # Overwrite same-named files in place so re-uploads don't proliferate copies
    dest = _PROMPTS_DIR / filename
    dest.write_bytes(contents)
    return _prompt_meta(dest)


@router.get("/file", response_class=PlainTextResponse)
def get_prompt_file(path: str) -> str:
    """Return the text content of a prompt file by absolute path."""
    p = Path(path).resolve()
    _PROMPTS_DIR.mkdir(exist_ok=True)
    prompts_dir_resolved = _PROMPTS_DIR.resolve()
    if not p.is_relative_to(prompts_dir_resolved) or p.suffix.lower() != ".md" or not p.exists():
        raise HTTPException(status_code=404, detail="Prompt file not found")
    return p.read_text(encoding="utf-8")


class PromptFileBody(BaseModel):
    content: str


@router.put("/file")
def put_prompt_file(path: str, body: PromptFileBody) -> dict:
    """Overwrite the content of a prompt file in place. Default prompts are immutable."""
    p = Path(path).resolve()
    _PROMPTS_DIR.mkdir(exist_ok=True)
    prompts_dir_resolved = _PROMPTS_DIR.resolve()
    defaults_dir = (prompts_dir_resolved / "defaults").resolve()
    if not p.is_relative_to(prompts_dir_resolved) or p.suffix.lower() != ".md" or not p.exists():
        raise HTTPException(status_code=404, detail="Prompt file not found")
    if p.is_relative_to(defaults_dir):
        raise HTTPException(status_code=403, detail="Default prompts are read-only")
    p.write_text(body.content, encoding="utf-8")
    return _prompt_meta(p)


class CreatePromptFileBody(BaseModel):
    filename: str
    content: str


@router.post("/file")
def create_prompt_file(body: CreatePromptFileBody) -> dict:
    """Create a new prompt file in prompts/. Fails if the file already exists."""
    filename = body.filename.strip()
    if not filename.lower().endswith(".md"):
        raise HTTPException(status_code=400, detail="Only .md files are accepted")
    _PROMPTS_DIR.mkdir(exist_ok=True)
    dest = (_PROMPTS_DIR / filename).resolve()
    if not dest.is_relative_to(_PROMPTS_DIR.resolve()):
        raise HTTPException(status_code=400, detail="Invalid filename")
    if dest.exists():
        raise HTTPException(status_code=409, detail="File already exists")
    dest.write_text(body.content, encoding="utf-8")
    return _prompt_meta(dest)
