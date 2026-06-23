"""Project a tree-v1 document into the minimal ResumeDocument the ATS gate reads
(header + section_order). The header feeds the mechanical contact checks; section_order
feeds the advisory semantic roundtrip (4C removed the mechanical section hard-block).
"""
from __future__ import annotations

from core.profile_tree import FieldNode, GroupNode, RootNode
from core.schemas import ResumeDocument, ResumeHeader


def _header_fields(root: RootNode) -> dict[str, str]:
    for s in root.children:
        if s.role == "header" and s.children and isinstance(s.children[0], GroupNode):
            out: dict[str, str] = {}
            for f in s.children[0].children:
                if isinstance(f, FieldNode) and isinstance(f.value, str):
                    out[f.key] = f.value.strip()
            return out
    return {}


def resume_document_for_ats(root: RootNode) -> ResumeDocument:
    """Minimal ``ResumeDocument`` for the ATS gate: header + section_order only."""
    hf = _header_fields(root)
    name = f"{hf.get('first_name', '')} {hf.get('last_name', '')}".strip()
    header = ResumeHeader(
        name=name,
        email=hf.get("email", ""),
        phone=hf.get("phone", ""),
        location=hf.get("location", ""),
        github=hf.get("github", ""),
        linkedin=hf.get("linkedin", ""),
        website=hf.get("website", ""),
    )
    section_order = [s.name.lower() for s in root.children if s.visible]
    return ResumeDocument(header=header, section_order=section_order)
