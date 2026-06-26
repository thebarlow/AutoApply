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


def _strip_url(url: str) -> str:
    """Display form of a URL: scheme and leading www. removed, trailing / dropped."""
    return (
        url.replace("https://www.", "").replace("http://www.", "")
        .replace("https://", "").replace("http://", "").rstrip("/")
    )


_HEADER_LINK_KEYS = {"github", "linkedin", "website"}


def _header_section_md(section: SectionNode) -> str:
    """Résumé header: name as H1, remaining contact fields as one ordered line.

    Name comes from ``first_name``/``last_name`` (joined). Remaining non-empty
    fields render in tree order as a ` · `-joined line; link-kind fields render as
    Markdown links with a scheme-stripped display. ATS-load-bearing order
    (email, phone, location, …) follows the tree's field order.
    """
    child = section.children[0] if section.children else None
    if not isinstance(child, GroupNode):
        return ""

    by_key = {f.key: f for f in child.children}

    def _val(f: FieldNode) -> str:
        v = f.value if isinstance(f.value, str) else ", ".join(str(x) for x in f.value)
        return v.strip()

    first = _val(by_key["first_name"]) if "first_name" in by_key else ""
    last = _val(by_key["last_name"]) if "last_name" in by_key else ""
    name = f"{first} {last}".strip()

    parts: list[str] = []
    for f in child.children:
        if f.key in ("first_name", "last_name"):
            continue
        val = _val(f)
        if not val:
            continue
        if f.key in _HEADER_LINK_KEYS:
            parts.append(f"[{_strip_url(val)}]({val})")
        else:
            parts.append(val)

    if not name and not parts:
        return ""
    lines = []
    if name:
        lines.append(f"# {name}")
    if parts:
        lines.append(" · ".join(parts))
    return "\n\n".join(lines)


def _list_rows(section: SectionNode) -> list[dict[str, object]]:
    """Per visible list entry, a ``{field key: value}`` dict; [] if not a list."""
    child = section.children[0] if section.children else None
    if not isinstance(child, ListNode):
        return []
    return [
        {f.key: f.value for f in entry.children}
        for entry in child.children
        if entry.visible
    ]


def _render_body(value: object) -> str:
    """Render an authored body value: a list → ``- `` bullet lines, else prose."""
    if isinstance(value, list):
        items = [str(x).strip() for x in value if str(x).strip()]
        return "\n".join(f"- {x}" for x in items)
    return str(value).strip()


def _experience_section_md(section: SectionNode) -> str:
    rows = _list_rows(section)
    if not rows:
        return ""
    parts = [f"## {section.name}"]
    for r in rows:
        dates = " – ".join(
            x for x in (str(r.get("start", "")).strip(), str(r.get("end", "")).strip()) if x
        )
        heading = f"### {str(r.get('title', '')).strip()}, {str(r.get('company', '')).strip()}".strip(", ")
        if dates:
            heading += f" ({dates})"
        block = heading
        summary = _render_body(r.get("summary", ""))
        if summary:
            block += "\n\n" + summary
        parts.append(block)
    return "\n\n".join(parts)


def _education_section_md(section: SectionNode) -> str:
    rows = _list_rows(section)
    if not rows:
        return ""
    lines = [f"## {section.name}"]
    for r in rows:
        line = (
            f"**{str(r.get('degree', '')).strip()} in {str(r.get('field', '')).strip()}**, "
            f"{str(r.get('institution', '')).strip()}"
        ).strip(", ")
        graduated = str(r.get("graduated", "")).strip()
        if graduated:
            line += f" ({graduated})"
        lines.append(line)
    return "\n\n".join(lines)


def _projects_section_md(section: SectionNode) -> str:
    rows = _list_rows(section)
    if not rows:
        return ""
    parts = [f"## {section.name}"]
    for r in rows:
        name = str(r.get("name", "")).strip()
        desc = str(r.get("description", "")).strip()
        nm = f"**{name}**" if name else ""
        parts.append(f"{nm}: {desc}".strip(": ") if nm else desc)
    return "\n\n".join(parts)


# Role → formatter. Populated by Tasks 3–4; default is the generic formatter.
_RENDERERS: dict[str, Callable[[SectionNode], str]] = {
    "header": _header_section_md,
    "summary": _summary_section_md,
    "skills": _skills_section_md,
    "experience": _experience_section_md,
    "education": _education_section_md,
    "projects": _projects_section_md,
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
