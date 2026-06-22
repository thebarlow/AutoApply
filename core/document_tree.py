"""Materialize a self-contained résumé *document tree* from the profile tree.

Pure module — no DB, no LLM, no filesystem. Given a profile ``RootNode`` and the
``field_id -> authored value`` map produced by ``core.section_generator``, returns
a NEW tree (deep copy) in which: invisible sections/entries/fields are removed;
context-only fields (``llm_input and not llm_output``) are removed; authored values
are baked into their fields by id; and locked nodes are carried through verbatim.
This pruned tree is the renderable, snapshot-safe résumé document.
"""
from __future__ import annotations

from core.profile_tree import (
    FieldNode, GroupNode, ListNode, RootNode, SectionNode, _coerce_field_value,
)

Value = "str | list[str]"


def _is_context_only(field: FieldNode) -> bool:
    """A field the LLM only reads (never written to the document)."""
    return field.llm_input and not field.llm_output


def _bake(field: FieldNode, authored: "dict[str, Value]") -> None:
    """Overlay an authored value onto a field, coercing to its kind's type."""
    if field.id in authored:
        field.value = _coerce_field_value(field.kind, authored[field.id])


def _prune_group(group: GroupNode, authored: "dict[str, Value]") -> None:
    """Drop invisible/context-only fields and bake authored values, in place."""
    kept: list[FieldNode] = []
    for f in group.children:
        if not f.visible or _is_context_only(f):
            continue
        _bake(f, authored)
        kept.append(f)
    group.children = kept


def build_resume_document_tree(
    root: RootNode, authored: "dict[str, Value]"
) -> RootNode:
    """Return a renderable document tree: pruned, value-baked deep copy of ``root``.

    Args:
        root: The profile tree (source structure).
        authored: ``field_node_id -> value`` from ``core.section_generator``.

    Returns:
        A new ``RootNode`` containing only visible, non-context-only nodes, with
        authored values baked in and locked nodes carried verbatim. ``root`` is
        not mutated.
    """
    doc = root.model_copy(deep=True)
    sections: list[SectionNode] = []
    for s in doc.children:
        if not s.visible:
            continue
        child = s.children[0] if s.children else None
        if isinstance(child, ListNode):
            entries = [e for e in child.children if e.visible]
            for e in entries:
                _prune_group(e, authored)
            child.children = entries
        elif isinstance(child, GroupNode):
            _prune_group(child, authored)
        elif isinstance(child, FieldNode):
            if not child.visible or _is_context_only(child):
                continue  # bare-field section with nothing to render → drop
            _bake(child, authored)
        sections.append(s)
    doc.children = sections
    return doc
