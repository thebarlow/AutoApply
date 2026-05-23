from __future__ import annotations

import uuid
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
    # Preserve original name; suffix with uuid hex if collision
    dest = _PROMPTS_DIR / filename
    if dest.exists():
        stem = Path(filename).stem
        dest = _PROMPTS_DIR / f"{stem}_{uuid.uuid4().hex[:6]}.md"
    dest.write_bytes(contents)
    return _prompt_meta(dest)


@router.get("/file", response_class=PlainTextResponse)
def get_prompt_file(path: str) -> str:
    """Return the text content of a prompt file by absolute path."""
    p = Path(path)
    if not p.exists() or p.suffix.lower() != ".md":
        raise HTTPException(status_code=404, detail="Prompt file not found")
    return p.read_text(encoding="utf-8")


class PromptFileBody(BaseModel):
    content: str


@router.put("/file")
def put_prompt_file(path: str, body: PromptFileBody) -> dict:
    """Overwrite the content of a prompt file in place."""
    p = Path(path)
    if not p.exists() or p.suffix.lower() != ".md":
        raise HTTPException(status_code=404, detail="Prompt file not found")
    p.write_text(body.content, encoding="utf-8")
    return _prompt_meta(p)
