from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from db.database import Account, get_db
from web.tenancy import current_profile_id

_DOCS_DIR = Path(__file__).parent.parent.parent / "Obsidian" / "Auto Apply" / "Docs"
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_ORDER_RE = re.compile(r"^order:\s*(\d+)", re.MULTILINE)
_TIERS_RE = re.compile(r"^tiers:\s*(.+)$", re.MULTILINE)

router = APIRouter(prefix="/api/docs", tags=["docs"])


def _frontmatter(path: Path) -> str:
    try:
        fm = _FRONTMATTER_RE.match(path.read_text(encoding="utf-8"))
        return fm.group(1) if fm else ""
    except OSError:
        return ""


def _parse_order(path: Path) -> int:
    m = _ORDER_RE.search(_frontmatter(path))
    return int(m.group(1)) if m else 9999


def _parse_tiers(path: Path) -> set[str] | None:
    """Tiers allowed to see a doc, or None if it's public (no ``tiers:`` key)."""
    m = _TIERS_RE.search(_frontmatter(path))
    if not m:
        return None
    return {t.strip() for t in m.group(1).split(",") if t.strip()}


def _caller_tier(db: Session, profile_id: int) -> tuple[str, bool]:
    """Return the caller's (tier, is_admin); defaults to standard/non-admin."""
    acct = db.query(Account).filter_by(profile_id=profile_id).first()
    if acct is None:
        return "standard", False
    return acct.tier, bool(acct.is_admin)


def _visible(path: Path, tier: str, is_admin: bool) -> bool:
    allowed = _parse_tiers(path)
    return allowed is None or is_admin or tier in allowed


@router.get("")
def list_docs(db: Session = Depends(get_db),
              profile_id: int = Depends(current_profile_id)) -> list[dict]:
    if not _DOCS_DIR.exists():
        return []
    tier, is_admin = _caller_tier(db, profile_id)
    files = sorted(_DOCS_DIR.glob("*.md"), key=_parse_order)
    return [{"filename": f.name, "title": f.stem}
            for f in files if _visible(f, tier, is_admin)]


@router.get("/{filename}")
def get_doc(filename: str, db: Session = Depends(get_db),
            profile_id: int = Depends(current_profile_id)) -> PlainTextResponse:
    if "/" in filename or "\\" in filename or not filename.endswith(".md"):
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = _DOCS_DIR / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    tier, is_admin = _caller_tier(db, profile_id)
    if not _visible(path, tier, is_admin):
        raise HTTPException(status_code=403, detail="Not available for your tier")
    text = path.read_text(encoding="utf-8")
    # Strip frontmatter before serving
    text = _FRONTMATTER_RE.sub("", text, count=1)
    return PlainTextResponse(text)
