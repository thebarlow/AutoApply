"""THROWAWAY renderer: profile tree -> readable Markdown for the Model 1 vs
Model 2 comparison harness only.

This is NOT the production schema-driven renderer (that is sub-project #4). It
exists only to make Model 2 output legible for side-by-side comparison; its
format is intentionally simple and may differ from the canonical assembler.
"""

from __future__ import annotations

from core.profile_tree import (
    FieldNode, GroupNode, ListNode, RootNode, SectionNode,
)

Authored = dict[str, "str | list[str]"]


def _is_context_only(f: FieldNode) -> bool:
    return f.llm_input and not f.llm_output


def _value(f: FieldNode, authored: Authored):
    """Authored value if present (outputable), else the stored value."""
    return authored.get(f.id, f.value)


def _render_field(f: FieldNode, authored: Authored) -> list[str]:
    if not f.visible or _is_context_only(f):
        return []
    val = _value(f, authored)
    if isinstance(val, list):
        if not val:
            return []
        return [f"- {item}" for item in val]
    if not str(val).strip():
        return []
    if f.kind == "markdown":
        return [str(val)]
    return [f"**{f.name}:** {val}"]


def _render_group(g: GroupNode, authored: Authored) -> list[str]:
    lines: list[str] = []
    for f in g.children:
        lines += _render_field(f, authored)
    return lines


def render_tree_markdown(root: RootNode, authored: Authored) -> str:
    """Render the tree to Markdown, overlaying ``authored`` onto outputable fields.

    Args:
        root: The profile tree.
        authored: ``field_node_id -> value`` from the section generator.

    Returns:
        Markdown string (no YAML front matter).
    """
    out: list[str] = []
    for section in root.children:
        if not section.visible:
            continue
        child = section.children[0] if section.children else None
        body: list[str] = []
        if isinstance(child, ListNode):
            for entry in child.children:
                if not entry.visible:
                    continue
                body += _render_group(entry, authored)
                body.append("")
        elif isinstance(child, GroupNode):
            body += _render_group(child, authored)
        elif isinstance(child, FieldNode):
            body += _render_field(child, authored)
        if not [ln for ln in body if ln.strip()]:
            continue
        out.append(f"## {section.name}")
        out.append("")
        out += body
        out.append("")
    return "\n".join(out).strip() + "\n"
