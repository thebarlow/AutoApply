"""Render a résumé *document tree* to Markdown via role-dispatched formatters.

Pure module — no DB, no LLM, no filesystem. Preset roles
(header/summary/experience/education/projects/skills) get fidelity-preserving
formatters that mirror ``core.document_assembler``; unknown/custom roles fall
through to ``_generic_section``. Section order is the tree's order — authoritative,
never canonically reordered. There is no YAML front matter; contact and education
are ordinary sections.
"""
from __future__ import annotations

from collections.abc import Callable

from core.profile_tree import (
    FieldNode, GroupNode, ListNode, RootNode, SectionNode,
)


def _render_field(field: FieldNode) -> list[str]:
    """Render one field to zero or more Markdown blocks."""
    val = field.value
    if isinstance(val, list):
        items = [str(x) for x in val if str(x).strip()]
        if not items:
            return []
        if field.kind == "taglist":
            return [f"**{field.name}:** {', '.join(items)}"]
        return ["\n".join(f"- {x}" for x in items)]
    text = str(val).strip()
    if not text:
        return []
    if field.kind == "markdown":
        return [text]
    return [f"**{field.name}:** {text}"]


def _render_group(group: GroupNode) -> list[str]:
    """Render all of a group's fields to a flat list of Markdown blocks."""
    out: list[str] = []
    for f in group.children:
        out += _render_field(f)
    return out


def _generic_section(section: SectionNode) -> str:
    """Render an arbitrary section: ``## name`` + body, or ``""`` if empty."""
    child = section.children[0] if section.children else None
    blocks: list[str] = []
    if isinstance(child, ListNode):
        for entry in child.children:
            eb = _render_group(entry)
            if eb:
                blocks.append("\n\n".join(eb))
    elif isinstance(child, GroupNode):
        eb = _render_group(child)
        if eb:
            blocks.append("\n\n".join(eb))
    elif isinstance(child, FieldNode):
        blocks += _render_field(child)
    if not blocks:
        return ""
    return f"## {section.name}\n\n" + "\n\n".join(blocks)


def _summary_section_md(section: SectionNode) -> str:
    """Profile summary: ``## name`` + the markdown field value."""
    child = section.children[0] if section.children else None
    if not isinstance(child, FieldNode):
        return ""
    text = str(child.value).strip()
    return f"## {section.name}\n\n{text}" if text else ""


def _skills_section_md(section: SectionNode) -> str:
    """Skills: ``## name`` + a single ``**label:** a, b, c`` line."""
    child = section.children[0] if section.children else None
    if not isinstance(child, FieldNode):
        return ""
    items = child.value if isinstance(child.value, list) else []
    items = [str(x) for x in items if str(x).strip()]
    if not items:
        return ""
    return f"## {section.name}\n\n**{child.name}:** {', '.join(items)}"


def _header_section_md(section: SectionNode) -> str:
    """Contact block: one ``**Label:** value`` block per non-empty field, in order."""
    child = section.children[0] if section.children else None
    if not isinstance(child, GroupNode):
        return ""
    blocks: list[str] = []
    for f in child.children:
        val = f.value if isinstance(f.value, str) else ", ".join(str(x) for x in f.value)
        val = val.strip()
        if val:
            blocks.append(f"**{f.name}:** {val}")
    if not blocks:
        return ""
    return f"## {section.name}\n\n" + "\n\n".join(blocks)


# Role → formatter. Populated by Tasks 3–4; default is the generic formatter.
_RENDERERS: dict[str, Callable[[SectionNode], str]] = {
    "header": _header_section_md,
    "summary": _summary_section_md,
    "skills": _skills_section_md,
}


def _render_section(section: SectionNode) -> str:
    fn = _RENDERERS.get(section.role or "", _generic_section)
    return fn(section).strip()


def assemble_resume_tree_markdown(root: RootNode) -> str:
    """Render a document tree to Markdown (no front matter).

    Args:
        root: A document tree (typically from ``build_resume_document_tree``).

    Returns:
        Canonical Markdown: visible sections in tree order, blank-line separated,
        with a trailing newline. Empty sections are omitted.
    """
    sections = [
        rendered
        for s in root.children
        if s.visible and (rendered := _render_section(s))
    ]
    return "\n\n".join(sections) + "\n"
