"""Build schema tree sections from parsed novel résumé sections (#5)."""
from __future__ import annotations

from core.profile_tree import FieldNode, GroupNode, ListNode, RootNode, SectionNode
from core.schemas import ExtraSection, ParsedEntry, ParseResponse

# ---------------------------------------------------------------------------
# Presence / emptiness helpers
# ---------------------------------------------------------------------------

_WRITABLE_KINDS = {"markdown", "bullets", "taglist"}

_HEADING_BY_ROLE: dict[str, str] = {
    "summary": "summary_heading",
    "experience": "work_history_heading",
    "education": "education_heading",
    "projects": "projects_heading",
    "skills": "skills_heading",
}


def _section_has_data(section: SectionNode) -> bool:
    """Return True if a SectionNode contains any non-empty user data.

    Inspects FieldNode values, ListNode children counts, and nested
    GroupNode children for non-empty fields.

    Args:
        section: The SectionNode to inspect.

    Returns:
        True if at least one child holds a non-empty value.
    """
    for child in section.children:
        child_type = getattr(child, "type", "")
        if child_type == "field":
            v = getattr(child, "value", None)
            if isinstance(v, list) and v:
                return True
            if isinstance(v, str) and v.strip():
                return True
        elif child_type == "list":
            if getattr(child, "children", None):
                return True
        elif child_type == "group":
            for f in getattr(child, "children", []):
                v = getattr(f, "value", None)
                if isinstance(v, str) and v.strip():
                    return True
                if isinstance(v, list) and v:
                    return True
    return False


def _item_name(role: str, values: dict) -> str:
    """Best-guess display name for one list item from its own field values.

    Args:
        role: The section role (e.g. "experience", "education", "projects").
        values: Mapping of field key/label → string value for this item.

    Returns:
        A human-readable name for the item, falling back to "<Role> Item".
    """
    def join(a: str, b: str, default: str) -> str:
        parts = [p for p in (a.strip(), b.strip()) if p]
        return " — ".join(parts) if parts else default

    if role == "experience":
        return join(values.get("company", ""), values.get("title", ""), "Experience Item")
    if role == "education":
        return join(values.get("institution", ""), values.get("degree", ""), "Education Item")
    if role == "projects":
        name = values.get("name", "").strip()
        return name or "Project Item"
    # novel list: first 1–2 non-empty values
    vals = [str(v).strip() for v in values.values() if str(v).strip()]
    return " — ".join(vals[:2]) if vals else "Item"


def iter_leaf_fields(section: SectionNode) -> list[FieldNode]:
    """All FieldNodes under a section (through groups, lists, and list templates).

    Args:
        section: The SectionNode to walk.

    Returns:
        Flat list of every FieldNode reachable from this section.
    """
    out: list[FieldNode] = []

    def walk(node) -> None:
        if isinstance(node, FieldNode):
            out.append(node)
        elif isinstance(node, GroupNode):
            for c in node.children:
                walk(c)
        elif isinstance(node, ListNode):
            for c in node.children:
                walk(c)
            walk(node.item_template)

    for child in section.children:
        walk(child)
    return out


def set_section_customize(section: SectionNode, customize: bool, prompt: str) -> None:
    """Toggle per-job tailoring: writable fields become llm_output; set/clear prompt.

    Args:
        section: The SectionNode to modify in-place.
        customize: If True, mark writable fields as LLM output and set prompt.
        prompt: Prompt string to attach (ignored when customize=False).
    """
    for f in iter_leaf_fields(section):
        if f.kind in _WRITABLE_KINDS:
            f.llm_output = customize
    section.prompt = prompt if customize else ""


def _rename_items(section: SectionNode) -> None:
    """Rename a list section's item GroupNodes to a best guess from their values.

    Args:
        section: The SectionNode whose ListNode children to rename.
    """
    for child in section.children:
        if isinstance(child, ListNode):
            for item in child.children:
                values = {f.key or f.name: (f.value if isinstance(f.value, str) else "")
                          for f in item.children}
                item.name = _item_name(section.role or "", values)


def _union_labels(entries: list[ParsedEntry]) -> list[str]:
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
    for entry_idx, e in enumerate(extra.entries):
        by_label = {f.label: f.value for f in e.fields}
        item_values = {lbl: by_label.get(lbl, "") for lbl in labels}
        # order must be unique across sibling items; validate_tree rejects a
        # ListNode whose children share an order (e.g. a multi-row CERTIFICATIONS
        # section), which otherwise 422s the parse/apply step.
        children.append(GroupNode(name=_item_name("", item_values), order=entry_idx, children=[
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
    """Return populated, heading-named, header-filtered preset sections from a ParseResponse.

    Post-processing applied to legacy_to_tree output:
    - Header section: empty fields removed; dropped if no fields remain.
    - Other sections: dropped if _section_has_data returns False.
    - Section names overridden by the résumé's heading fields when present.
    - List item GroupNodes renamed via _item_name for best-guess display.
    - order re-indexed to match final kept order.

    Args:
        parsed: A validated ParseResponse from the résumé parser.

    Returns:
        List of SectionNodes ready for profile-tree insertion.
    """
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

    kept: list[SectionNode] = []
    for s in root.children:
        if s.role == "header":
            # Filter empty fields from the header group
            group = s.children[0] if s.children else None
            if group is not None and isinstance(group, GroupNode):
                group.children = [f for f in group.children if (f.value or "").strip()]
                if not group.children:
                    continue
            kept.append(s)
            continue

        # Drop sections with no data
        if not _section_has_data(s):
            continue

        # Override section name from résumé heading field
        heading_attr = _HEADING_BY_ROLE.get(s.role or "")
        if heading_attr:
            heading = getattr(parsed, heading_attr, "") or ""
            if heading.strip():
                s.name = heading.strip()

        _rename_items(s)
        kept.append(s)

    for i, s in enumerate(kept):
        s.order = i

    return kept


def build_onboarding_root(proposal) -> RootNode:
    """Build a fresh RootNode from a ParseProposal's selected sections (intake).

    Sections are taken in proposal order; builtin sections come heading-named and
    presence-filtered from ``builtin_sections_from_parse``; novel sections from
    ``build_section_from_parsed``. Each section's ``customize``/``prompt`` choice
    is applied. Verbatim sections keep ``llm_output=False``.

    Args:
        proposal: A ``ParseProposal`` with ``builtin``, ``extra_sections``, and
            ``sections`` (ordered list of ``ProposedSection`` rows).

    Returns:
        A fresh ``RootNode`` containing only the selected, populated sections.
    """
    builtin_by_role = {s.role: s for s in builtin_sections_from_parse(proposal.builtin) if s.role}
    root = RootNode()
    order = 0
    for r in proposal.sections:
        if r.origin == "builtin":
            section = builtin_by_role.get(r.builtin_role)
            if section is None:
                continue
        else:
            if r.extra_index < 0 or r.extra_index >= len(proposal.extra_sections):
                continue
            section = build_section_from_parsed(proposal.extra_sections[r.extra_index])
            if r.name and r.name != section.name:
                section.name = r.name
        set_section_customize(section, bool(r.customize), r.prompt or "")
        section.order = order
        order += 1
        root.children.append(section)
    return root


def find_section(root: RootNode, *, name: str = "", role: str = "") -> SectionNode | None:
    """Find a section by ``role`` (when given) or case-folded ``name``."""
    for s in root.children:
        if role and s.role == role:
            return s
        if name and s.name.casefold() == name.casefold():
            return s
    return None


def add_section(root: RootNode, section: SectionNode) -> None:
    """Append ``section`` to the root, stamping it with the next order."""
    section.order = len(root.children)
    root.children.append(section)


def replace_section(existing: SectionNode, incoming: SectionNode) -> None:
    """Swap ``existing``'s children for ``incoming``'s, preserving id/name/role."""
    existing.children = incoming.children


def _single_field(section: SectionNode, kind: str) -> FieldNode | None:
    child = section.children[0] if len(section.children) == 1 else None
    if isinstance(child, FieldNode) and child.kind == kind:
        return child
    return None


def _list_node(section: SectionNode) -> ListNode | None:
    child = section.children[0] if section.children else None
    return child if isinstance(child, ListNode) else None


def merge_section(existing: SectionNode, incoming: SectionNode) -> None:
    """Merge ``incoming`` into ``existing`` for mergeable shapes.

    list → append records; taglist → case-insensitive union; bullets → append.
    Raises ValueError for any other (non-mergeable) shape.
    """
    el, il = _list_node(existing), _list_node(incoming)
    if el is not None and il is not None:
        el.children.extend(il.children)
        # Re-index sibling order: both lists number their items from 0, so a raw
        # extend collides (validate_tree rejects duplicate sibling order → 422).
        for i, item in enumerate(el.children):
            item.order = i
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
