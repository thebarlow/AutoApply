"""Pure renderers: structured document models → canonical Markdown body.

No database, no LLM. The canonical résumé section order is backend-owned and
fixed here, which is what makes section misordering structurally impossible.
"""
from __future__ import annotations

from core.schemas import CoverDocument, ResumeDocument

# Canonical résumé section order. Sections with no content are omitted.
CANONICAL_SECTIONS: list[str] = ["Profile", "Experience", "Education", "Projects", "Skills"]


def _profile_section(doc: ResumeDocument) -> str:
    if not doc.profile_summary.strip():
        return ""
    return "## Profile\n\n" + doc.profile_summary.strip()


def _experience_section(doc: ResumeDocument) -> str:
    if not doc.experience:
        return ""
    parts: list[str] = ["## Experience"]
    for e in doc.experience:
        dates = " – ".join(filter(None, [e.start, e.end]))
        heading = f"### {e.title}, {e.company}".strip(", ")
        if dates:
            heading += f" ({dates})"
        block = heading
        if e.description.strip():
            block += "\n\n" + e.description.strip()
        parts.append(block)
    return "\n\n".join(parts)


def _education_section(doc: ResumeDocument) -> str:
    if not doc.education:
        return ""
    lines = ["## Education"]
    for ed in doc.education:
        line = f"**{ed.degree} in {ed.field}**, {ed.institution}".strip(", ")
        if ed.graduated:
            line += f" ({ed.graduated})"
        lines.append(line)
    return "\n\n".join(lines)


def _projects_section(doc: ResumeDocument) -> str:
    if not doc.projects:
        return ""
    parts = ["## Projects"]
    for p in doc.projects:
        name = f"**{p.name}**" if p.name else ""
        desc = p.description.strip()
        line = f"{name}: {desc}".strip(": ") if name else desc
        parts.append(line)
    return "\n\n".join(parts)


def _skills_section(doc: ResumeDocument) -> str:
    groups = [g for g in doc.skills if g.items]
    if not groups:
        return ""
    lines = ["## Skills"]
    for g in groups:
        lines.append(f"**{g.category}:** {', '.join(g.items)}")
    return "\n\n".join(lines)


_SECTION_RENDERERS = {
    "Profile": _profile_section,
    "Experience": _experience_section,
    "Education": _education_section,
    "Projects": _projects_section,
    "Skills": _skills_section,
}


def resume_section_order(doc: ResumeDocument) -> list[str]:
    """Return the canonical-ordered names of sections that have content."""
    return [
        name for name in CANONICAL_SECTIONS
        if _SECTION_RENDERERS[name](doc).strip()
    ]


def assemble_resume_markdown(doc: ResumeDocument) -> str:
    """Render a ResumeDocument to canonical-ordered Markdown (no front matter)."""
    sections = [
        rendered
        for name in CANONICAL_SECTIONS
        if (rendered := _SECTION_RENDERERS[name](doc).strip())
    ]
    return "\n\n".join(sections) + "\n"


def assemble_cover_markdown(doc: CoverDocument) -> str:
    """Render a CoverDocument to Markdown: body, then sign-off (no front matter)."""
    body = doc.body.strip()
    signoff = doc.signoff.name.strip()
    if signoff:
        return f"{body}\n\n{signoff}\n"
    return body + "\n"
