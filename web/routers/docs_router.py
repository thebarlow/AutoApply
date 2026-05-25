from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

_DOCS_DIR = Path(__file__).parent.parent.parent / "Obsidian" / "Auto Apply" / "Docs"

router = APIRouter(prefix="/api/docs", tags=["docs"])


@router.get("")
def list_docs() -> list[dict]:
    if not _DOCS_DIR.exists():
        return []
    return [
        {"filename": f.name, "title": f.stem}
        for f in sorted(_DOCS_DIR.glob("*.md"))
    ]


@router.get("/{filename}")
def get_doc(filename: str) -> PlainTextResponse:
    if "/" in filename or "\\" in filename or not filename.endswith(".md"):
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = _DOCS_DIR / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return PlainTextResponse(path.read_text(encoding="utf-8"))
