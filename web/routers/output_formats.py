from __future__ import annotations

from fastapi import APIRouter

from core.output_formats import all_formats

router = APIRouter()


@router.get("/api/output-formats")
def list_output_formats() -> list[dict[str, str]]:
    """The output-format registry for the profile-tree format picker."""
    return [{"id": f.id, "label": f.label, "kind": f.kind} for f in all_formats()]
