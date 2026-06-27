"""Build schema tree sections from parsed novel résumé sections (#5)."""
from __future__ import annotations

from core.profile_tree import FieldNode, GroupNode, ListNode, RootNode, SectionNode
from core.schemas import ExtraSection, ParseResponse


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


# ---------------------------------------------------------------------------
# Tree apply operations
# ---------------------------------------------------------------------------

def builtin_sections_from_parse(parsed: ParseResponse) -> list[SectionNode]:
    """Return the preset SectionNodes (with roles) from a ParseResponse's fixed fields."""
    from core.profile_tree import legacy_to_tree

    flat: dict = {
        "first_name": parsed.first_name,
        "last_name": parsed.last_name,
        "hero": parsed.hero,
        "email": parsed.email,
        "phone": parsed.phone,
        "location": parsed.location,
        "github": parsed.github,
        "linkedin": parsed.linkedin,
        "website": parsed.website,
        "skills": list(parsed.skills or []),
        "work_history": [e.model_dump() if hasattr(e, "model_dump") else e
                         for e in (parsed.work_history or [])],
        "education": [e.model_dump() if hasattr(e, "model_dump") else e
                      for e in (parsed.education or [])],
        "projects": [e.model_dump() if hasattr(e, "model_dump") else e
                     for e in (parsed.projects or [])],
    }
    root = legacy_to_tree(flat)
    return root.children


def find_section(root: RootNode, *, name: str = "", role: str = "") -> SectionNode | None:
    for s in root.children:
        if role and s.role == role:
            return s
        if name and s.name.casefold() == name.casefold():
            return s
    return None


def add_section(root: RootNode, section: SectionNode) -> None:
    section.order = len(root.children)
    root.children.append(section)


def replace_section(existing: SectionNode, incoming: SectionNode) -> None:
    existing.children = incoming.children


def _single_field(section: SectionNode, kind: str) -> FieldNode | None:
    if len(section.children) == 1 and getattr(section.children[0], "type", "") == "field" \
            and section.children[0].kind == kind:
        return section.children[0]
    return None


def _list_node(section: SectionNode) -> ListNode | None:
    if section.children and getattr(section.children[0], "type", "") == "list":
        return section.children[0]
    return None


def merge_section(existing: SectionNode, incoming: SectionNode) -> None:
    el, il = _list_node(existing), _list_node(incoming)
    if el is not None and il is not None:
        el.children.extend(il.children)
        return
    for kind, combine in (("taglist", _union), ("bullets", _append)):
        ef, inf = _single_field(existing, kind), _single_field(incoming, kind)
        if ef is not None and inf is not None:
            ef.value = combine(ef.value, inf.value)
            return
    raise ValueError("section shape is not mergeable")


def _union(a: list, b: list) -> list:
    out = list(a)
    seen = {x.casefold() for x in a}
    for x in b:
        if x.casefold() not in seen:
            out.append(x)
            seen.add(x.casefold())
    return out


def _append(a: list, b: list) -> list:
    return list(a) + list(b)
