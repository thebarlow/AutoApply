from __future__ import annotations

from fastapi import APIRouter

from generator.themes import all_themes

router = APIRouter()


@router.get("/api/themes")
def list_themes() -> list[dict[str, str]]:
    """The résumé theme registry for the profile-editor theme picker."""
    return [{"id": t.id, "label": t.label} for t in all_themes()]
