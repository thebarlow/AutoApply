"""Materialize a self-contained résumé *document tree* from the profile tree.

Pure module — no DB, no LLM, no filesystem. Given a profile ``RootNode`` and the
``field_id -> authored value`` map produced by ``core.section_generator``, returns
a NEW tree (deep copy) in which: invisible sections/entries/fields are removed;
context-only fields (``llm_input and not llm_output``) are removed; authored values
are baked into their fields by id; and locked nodes are carried through verbatim.
This pruned tree is the renderable, snapshot-safe résumé document.
"""
from __future__ import annotations

from core.output_formats import get_format
from core.profile_tree import (
    FieldNode, GroupNode, ListNode, RootNode, SectionNode, _coerce_field_value,
)

Value = str | list[str]


def _is_context_only(field: FieldNode) -> bool:
    """A field the LLM only reads (never written to the document)."""
    return field.llm_input and not field.llm_output


def _bake(field: FieldNode, authored: dict[str, Value]) -> None:
    """Overlay an authored value onto a field, coercing to its kind's type.

    When the field declares an ``output_format`` whose storage ``kind`` differs
    from the field's own kind (e.g. a ``taglist`` skills inventory authored as a
    grouped ``markdown`` block), the *document* field adopts the format's kind so
    the authored value survives baking. The source profile field is untouched —
    this operates on the deep-copied document tree only.
    """
    if field.id not in authored:
        return
    fmt = get_format(getattr(field, "output_format", "") or "")
    if fmt is not None and fmt.kind != field.kind:
        field.kind = fmt.kind  # type: ignore[assignment]  # format kinds are valid FieldNode kinds
    field.value = _coerce_field_value(field.kind, authored[field.id])


def _prune_group(group: GroupNode, authored: dict[str, Value]) -> None:
    """Drop invisible/context-only fields and bake authored values, in place."""
    kept: list[FieldNode] = []
    for f in group.children:
        if not f.visible or _is_context_only(f):
            continue
        _bake(f, authored)
        kept.append(f)
    group.children = kept


def authored_values_from_tree(root: RootNode) -> dict[str, Value]:
    """``field_id -> value`` for every ``llm_output`` field anywhere in the tree.

    Seeds the cumulative authored map so per-section refinement can regenerate
    only failing sections while passing sections keep their current values.
    """
    out: dict[str, Value] = {}

    def _visit_group(group: GroupNode) -> None:
        for f in group.children:
            if f.llm_output:
                out[f.id] = f.value

    for s in root.children:
        child = s.children[0] if s.children else None
        if isinstance(child, ListNode):
            for entry in child.children:
                _visit_group(entry)
        elif isinstance(child, GroupNode):
            _visit_group(child)
        elif isinstance(child, FieldNode):
            if child.llm_output:
                out[child.id] = child.value
    return out


def build_resume_document_tree(
    root: RootNode, authored: dict[str, Value]
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
        # Locked sections are carried through verbatim (not pruned or baked).
        if s.locked:
            sections.append(s)
            continue
        child = s.children[0] if s.children else None
        if isinstance(child, ListNode):
            entries = [e for e in child.children if e.visible]
            for e in entries:
                if not e.locked:
                    _prune_group(e, authored)
            from core.section_generator import ORDER_PREFIX  # lazy: avoid import cycle

            ranked = authored.get(f"{ORDER_PREFIX}{s.id}")
            if isinstance(ranked, list):
                pos = {eid: i for i, eid in enumerate(ranked)}
                # Ranked entries first (in model order); unranked keep relative order.
                entries.sort(key=lambda e: pos.get(e.id, len(pos)))
            child.children = entries
        elif isinstance(child, GroupNode):
            if not child.locked:
                _prune_group(child, authored)
        elif isinstance(child, FieldNode):
            if not child.visible or _is_context_only(child):
                continue  # bare-field section with nothing to render → drop
            _bake(child, authored)
        sections.append(s)
    doc.children = sections
    return doc
