"""Build schema tree sections from parsed novel résumé sections (#5)."""
from __future__ import annotations

from core.profile_tree import FieldNode, GroupNode, ListNode, SectionNode
from core.schemas import ExtraSection


def _union_labels(entries) -> list[str]:
    seen: list[str] = []
    for e in entries:
        for f in e.fields:
            if f.label and f.label not in seen:
                seen.append(f.label)
    return seen


def build_section_from_parsed(extra: ExtraSection, order: int = 0) -> SectionNode:
    """Convert a parsed novel section into a generic (role="") SectionNode.

    Field nodes are ``llm_output=False`` — parsed factual content is verbatim,
    not LLM-authored.
    """
    name = extra.name or "Section"
    if extra.kind in ("markdown", "bullets", "taglist"):
        value = extra.markdown if extra.kind == "markdown" else list(extra.items)
        field = FieldNode(name=name, kind=extra.kind, value=value, llm_output=False)
        return SectionNode(name=name, role="", order=order, children=[field])

    if extra.kind == "fields":
        fields = [FieldNode(name=f.label or f"Field {i+1}", kind="text",
                            value=f.value, order=i, llm_output=False)
                  for i, f in enumerate(extra.fields)]
        return SectionNode(name=name, role="", order=order,
                           children=[GroupNode(name=name, children=fields)])

    # kind == "list"
    labels = _union_labels(extra.entries)
    template = GroupNode(name=f"{name} Item", children=[
        FieldNode(name=lbl, kind="text", order=i, llm_output=False)
        for i, lbl in enumerate(labels)
    ])
    children = []
    for e in extra.entries:
        by_label = {f.label: f.value for f in e.fields}
        children.append(GroupNode(name=f"{name} Item", children=[
            FieldNode(name=lbl, kind="text", order=i, value=by_label.get(lbl, ""),
                      llm_output=False)
            for i, lbl in enumerate(labels)
        ]))
    lst = ListNode(name=name, item_template=template, children=children)
    return SectionNode(name=name, role="", order=order, children=[lst])
