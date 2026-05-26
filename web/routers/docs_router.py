from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

_DOCS_DIR = Path(__file__).parent.parent.parent / "Obsidian" / "Auto Apply" / "Docs"
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_ORDER_RE = re.compile(r"^order:\s*(\d+)", re.MULTILINE)

router = APIRouter(prefix="/api/docs", tags=["docs"])


def _parse_order(path: Path) -> int:
    try:
        text = path.read_text(encoding="utf-8")
        fm = _FRONTMATTER_RE.match(text)
        if fm:
            m = _ORDER_RE.search(fm.group(1))
            if m:
                return int(m.group(1))
    except OSError:
        pass
    return 9999


@router.get("")
def list_docs() -> list[dict]:
    if not _DOCS_DIR.exists():
        return []
    files = sorted(_DOCS_DIR.glob("*.md"), key=_parse_order)
    return [{"filename": f.name, "title": f.stem} for f in files]


@router.get("/{filename}")
def get_doc(filename: str) -> PlainTextResponse:
    if "/" in filename or "\\" in filename or not filename.endswith(".md"):
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = _DOCS_DIR / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    text = path.read_text(encoding="utf-8")
    # Strip frontmatter before serving
    text = _FRONTMATTER_RE.sub("", text, count=1)
    return PlainTextResponse(text)
