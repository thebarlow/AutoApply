"""Recursive, typed profile/résumé tree: closed node vocabulary.

Pure module — no DB, no LLM. Provides ``FieldNode``, ``GroupNode``,
``ListNode``, ``SectionNode``, and ``RootNode`` — the complete vocabulary for
representing a structured profile/résumé tree.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from typing import Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator


def _new_id() -> str:
    """Return a fresh hex node id."""
    return uuid.uuid4().hex


class FieldNode(BaseModel):
    """A leaf value. ``key`` is the stable machine identifier (rename-safe)."""

    type: Literal["field"] = "field"
    id: str = Field(default_factory=_new_id)
    name: str = ""
    key: str = ""
    order: int = 0
    visible: bool = True
    kind: Literal["text", "markdown", "bullets", "taglist"] = "text"
    value: Union[str, list[str]] = ""
    llm_output: bool = False
    llm_instructions: str = ""
    llm_input: bool = False
    regen_lock: bool = False
    min: Optional[int] = None
    max: Optional[int] = None

    @field_validator("value", mode="before")
    @classmethod
    def _normalize_value(cls, v, info):
        kind = info.data.get("kind", "text")
        if kind in ("text", "markdown"):
            if isinstance(v, list):
                return " ".join(str(x) for x in v)
            return "" if v is None else str(v)
        # bullets, taglist
        if isinstance(v, str):
            return [v] if v else []
        if v is None:
            return []
        return [str(x) for x in v]


class GroupNode(BaseModel):
    """A bundle of fields; also serves as a list's item instance/template."""

    type: Literal["group"] = "group"
    id: str = Field(default_factory=_new_id)
    name: str = ""
    order: int = 0
    visible: bool = True
    locked: bool = False
    prompt: str = ""
    children: list[FieldNode] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _migrate_regen_lock(cls, data):
        """Legacy trees stored a group's pin as ``regen_lock``; fold it into the
        new ``locked`` gate unless ``locked`` is already given explicitly.
        """
        if isinstance(data, dict) and "locked" not in data and data.get("regen_lock"):
            data = {**data, "locked": True}
        return data


class ListNode(BaseModel):
    """A repeating container; every child conforms to ``item_template``."""

    type: Literal["list"] = "list"
    id: str = Field(default_factory=_new_id)
    name: str = ""
    order: int = 0
    visible: bool = True
    bullet_style: str = "none"
    item_template: GroupNode = Field(default_factory=GroupNode)
    children: list[GroupNode] = Field(default_factory=list)


SectionChild = Union[ListNode, GroupNode, FieldNode]


class SectionNode(BaseModel):
    """A top-level block. ``role`` ties presets to the legacy adapter."""

    type: Literal["section"] = "section"
    id: str = Field(default_factory=_new_id)
    name: str = ""
    role: Optional[str] = None
    order: int = 0
    visible: bool = True
    locked: bool = False
    prompt: str = ""
    children: list[SectionChild] = Field(default_factory=list)


class RootNode(BaseModel):
    """The profile/résumé root."""

    type: Literal["root"] = "root"
    id: str = Field(default_factory=_new_id)
    children: list[SectionNode] = Field(default_factory=list)


class TreeValidationError(Exception):
    """Raised when a profile tree violates a structural invariant."""


def _shape(group: GroupNode) -> list[tuple[str, str]]:
    """Return the sorted ``(key, kind)`` multiset that defines a group's shape."""
    return sorted((f.key, f.kind) for f in group.children)


def validate_tree(root: RootNode) -> None:
    """Validate structural invariants of a profile tree.

    Args:
        root: The tree to validate.

    Raises:
        TreeValidationError: If any invariant is violated.
    """
    seen_ids: set[str] = set()

    _AnyNode = Union[RootNode, SectionNode, ListNode, GroupNode, FieldNode]

    def visit(node: "_AnyNode") -> None:
        nid = getattr(node, "id", None)
        if nid is not None:
            if nid in seen_ids:
                raise TreeValidationError(f"Duplicate node id: {nid}")
            seen_ids.add(nid)

        if isinstance(node, GroupNode):
            keys = [f.key for f in node.children]
            if len(set(keys)) != len(keys):
                raise TreeValidationError(f"Duplicate field key in group {node.name!r}")

        if isinstance(node, FieldNode) and node.kind == "bullets":
            if (node.min is not None and node.min < 0) or (
                node.min is not None and node.max is not None and node.min > node.max
            ):
                raise TreeValidationError(
                    f"Invalid bullets bounds in field {node.name!r}"
                )

        if isinstance(node, SectionNode):
            if len(node.children) != 1:
                raise TreeValidationError(
                    f"Section {node.name!r} must have exactly one child"
                )

        if isinstance(node, ListNode):
            tmpl_shape = _shape(node.item_template)
            for item in node.children:
                if _shape(item) != tmpl_shape:
                    raise TreeValidationError(
                        f"List {node.name!r} item does not conform to item_template"
                    )
            # Visit template separately to validate its structure (but not as a sibling)
            visit(node.item_template)

        children = getattr(node, "children", None)
        if children is not None:
            if isinstance(node, (RootNode, SectionNode, ListNode)):
                orders = [getattr(c, "order", 0) for c in children]
                if len(set(orders)) != len(orders):
                    raise TreeValidationError("Duplicate sibling order")
            for c in children:
                visit(c)

    visit(root)


def _gpa_to_str(v: object) -> str:
    """Convert a legacy GPA value to its string form ("" only for unset)."""
    if v is None or v == "":
        return ""
    return str(v)


def legacy_to_tree(data: dict) -> "RootNode":
    """Build the default preset tree from a legacy flat profile dict.

    Args:
        data: Legacy profile dict with top-level keys like first_name, hero,
            work_history, education, projects, skills.

    Returns:
        A RootNode with fully populated preset sections.
    """
    from core.section_presets import (
        education_template,
        experience_template,
        header_section,
        projects_template,
        skills_section,
        summary_section,
    )

    def _instances(
        rows: list[dict],
        template: GroupNode,
        mapper: Callable[[dict], dict],
    ) -> list[GroupNode]:
        items: list[GroupNode] = []
        for i, row in enumerate(rows or []):
            vals = mapper(row)
            fields = [
                FieldNode(
                    name=t.name,
                    key=t.key,
                    kind=t.kind,
                    order=t.order,
                    llm_output=t.llm_output,
                    value=vals.get(t.key, ""),
                )
                for t in template.children
            ]
            items.append(GroupNode(name=template.name, order=i, children=fields))
        return items

    header = header_section()
    for f in header.children[0].children:
        f.value = data.get(f.key, "") or ""

    summary = summary_section()
    summary.children[0].value = data.get("hero", "") or ""

    exp_tmpl = experience_template()
    experience = SectionNode(
        name="Experience",
        role="experience",
        order=2,
        children=[
            ListNode(
                name="Experience",
                item_template=exp_tmpl,
                children=_instances(data.get("work_history"), exp_tmpl, lambda r: r),
            )
        ],
    )

    edu_tmpl = education_template()
    education = SectionNode(
        name="Education",
        role="education",
        order=3,
        children=[
            ListNode(
                name="Education",
                item_template=edu_tmpl,
                children=_instances(
                    data.get("education"),
                    edu_tmpl,
                    lambda r: {**r, "gpa": _gpa_to_str(r.get("gpa"))},
                ),
            )
        ],
    )

    proj_tmpl = projects_template()
    projects = SectionNode(
        name="Projects",
        role="projects",
        order=4,
        children=[
            ListNode(
                name="Projects",
                item_template=proj_tmpl,
                children=_instances(data.get("projects"), proj_tmpl, lambda r: r),
            )
        ],
    )

    skills = skills_section()
    skills.children[0].value = list(data.get("skills") or [])

    root = RootNode(children=[header, summary, experience, education, projects, skills])
    return root


def merge_flat_into_stored(existing_data: dict, new_flat: dict) -> dict:
    """Return the dict to persist: ``new_flat`` plus a tree with flat overlaid.

    Picks the base tree from ``existing_data['profile_tree']`` when present
    (preserving its IDs and tree-only data); otherwise builds one from the
    merged flat via ``legacy_to_tree``. Any ``profile_tree`` inside ``new_flat``
    is ignored (the stored tree is authoritative). The flat doc-section fields
    are overlaid onto the base tree in place.

    Args:
        existing_data: The currently stored profile dict (may have profile_tree).
        new_flat: The new flat profile dict to persist.

    Returns:
        ``new_flat`` (minus any stale profile_tree) plus a fresh ``profile_tree``.
    """
    base = existing_data.get("profile_tree")
    if base:
        tree = RootNode.model_validate(base)
    else:
        tree = legacy_to_tree({**existing_data, **new_flat})
    out = dict(new_flat)
    out.pop("profile_tree", None)
    apply_flat_to_tree(tree, out)
    validate_tree(tree)
    out["profile_tree"] = tree.model_dump(mode="json")
    return out


def validate_tree_limits(
    root: "RootNode", *, max_nodes: int = 500, max_depth: int = 6
) -> None:
    """Raise TreeValidationError if the tree is too large or too deep.

    Root is depth 0; a ListNode's item_template counts as a node one level
    below the list. Guards the PUT endpoint against abusive/runaway trees.

    Args:
        root: The tree to validate.
        max_nodes: Maximum total node count (default 500).
        max_depth: Maximum depth, root = 0 (default 6).

    Raises:
        TreeValidationError: If the tree exceeds the node count or depth caps.
    """
    count = 0

    def walk(node: object, depth: int) -> None:
        nonlocal count
        count += 1
        if depth > max_depth:
            raise TreeValidationError(f"Tree exceeds max depth {max_depth}")
        for c in (getattr(node, "children", None) or []):
            walk(c, depth + 1)
        if isinstance(node, ListNode):
            walk(node.item_template, depth + 1)

    walk(root, 0)
    if count > max_nodes:
        raise TreeValidationError(f"Tree exceeds max nodes {max_nodes}")


def _section_by_role(root: "RootNode", role: str) -> Optional[SectionNode]:
    """Return the first SectionNode whose role matches, or None."""
    for s in root.children:
        if s.role == role:
            return s
    return None


def _gpa_to_float(v: object) -> float:
    """Convert a stored GPA string/number to float.

    Returns 0.0 when v is absent, empty, or non-numeric. Note: a genuine GPA
    of 0.0 is indistinguishable from an absent GPA after this conversion.
    """
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


# Role → flat list key for the repeating sections.
_LIST_ROLE_FLATKEY = {
    "experience": "work_history",
    "education": "education",
    "projects": "projects",
}


def _coerce_field_value(kind: str, raw: object) -> "str | list[str]":
    """Coerce a raw value to the Python type a FieldNode of ``kind`` stores.

    Mirrors FieldNode's value normalizer, for use on direct attribute
    assignment (Pydantic v2 does not re-validate on assignment).
    """
    if kind in ("text", "markdown"):
        if isinstance(raw, list):
            return " ".join(str(x) for x in raw)
        return "" if raw is None else str(raw)
    if isinstance(raw, str):
        return [raw] if raw else []
    if raw is None:
        return []
    return [str(x) for x in raw]


def _row_for_role(role: str, row: dict) -> dict:
    """Apply per-role flat-row value conversions (education gpa → str)."""
    if role == "education":
        return {**row, "gpa": _gpa_to_str(row.get("gpa"))}
    return row


def _overlay_group(group: GroupNode, row: dict) -> None:
    """Update a group's field values from ``row``, by key, preserving IDs.

    Only keys present in ``row`` are written; other fields (incl. tree-only
    custom fields) are left untouched.
    """
    for f in group.children:
        if f.key in row:
            f.value = _coerce_field_value(f.kind, row[f.key])


def _new_item_from_template(template: GroupNode, row: dict) -> GroupNode:
    """Clone a list's item_template into a fresh item populated from ``row``."""
    item = template.model_copy(deep=True)
    item.id = _new_id()
    for f in item.children:
        f.id = _new_id()
        if f.key in row:
            f.value = _coerce_field_value(f.kind, row[f.key])
    return item


def apply_flat_to_tree(tree: "RootNode", flat: dict) -> "RootNode":
    """Overlay flat doc-section fields onto an existing tree, in place.

    Scalars (header contact, summary ``hero``, ``skills``) are matched by
    ``(role, key)``; list sections (experience/education/projects) are matched
    by index — existing items updated in place (IDs preserved), extra flat rows
    appended (cloned from item_template with fresh IDs), trailing items removed.
    Only flat keys that are present are written, so custom (``role is None``)
    sections and tree-only fields/attributes survive untouched.

    Args:
        tree: The existing tree to mutate.
        flat: A flat profile dict (subset is fine; absent keys are skipped).

    Returns:
        The same ``tree`` instance, mutated.
    """
    header = _section_by_role(tree, "header")
    if header and header.children and isinstance(header.children[0], GroupNode):
        for f in header.children[0].children:
            if f.key in flat:
                f.value = _coerce_field_value(f.kind, flat[f.key])

    summary = _section_by_role(tree, "summary")
    if summary and summary.children and isinstance(summary.children[0], FieldNode):
        if "hero" in flat:
            summary.children[0].value = _coerce_field_value(summary.children[0].kind, flat["hero"])

    skills = _section_by_role(tree, "skills")
    if skills and skills.children and isinstance(skills.children[0], FieldNode):
        if "skills" in flat:
            skills.children[0].value = _coerce_field_value(skills.children[0].kind, flat["skills"])

    for role, fkey in _LIST_ROLE_FLATKEY.items():
        if fkey not in flat:
            continue
        sect = _section_by_role(tree, role)
        if not sect or not sect.children or not isinstance(sect.children[0], ListNode):
            continue
        lst = sect.children[0]
        rows = [_row_for_role(role, r) for r in (flat.get(fkey) or [])]
        for i, row in enumerate(rows):
            if i < len(lst.children):
                _overlay_group(lst.children[i], row)
            else:
                new_item = _new_item_from_template(lst.item_template, row)
                new_item.order = i
                lst.children.append(new_item)
        if len(rows) < len(lst.children):
            del lst.children[len(rows):]

    return tree


def tree_to_legacy(root: "RootNode") -> dict:
    """Project a profile tree into the legacy flat document-section dict.

    Args:
        root: A fully populated RootNode (e.g. from ``legacy_to_tree``).

    Returns:
        Dict with keys matching the legacy profile/document surface:
        ``first_name``, ``last_name``, ``hero``, ``email``, ``phone``,
        ``location``, ``github``, ``linkedin``, ``website``, ``skills``,
        ``work_history``, ``education``, ``projects``.
    """
    out: dict = {
        "first_name": "",
        "last_name": "",
        "hero": "",
        "email": "",
        "phone": "",
        "location": "",
        "github": "",
        "linkedin": "",
        "website": "",
        "skills": [],
        "work_history": [],
        "education": [],
        "projects": [],
    }

    header = _section_by_role(root, "header")
    if header and header.visible and header.children and isinstance(header.children[0], GroupNode):
        for f in header.children[0].children:
            if f.visible and f.key in out:
                out[f.key] = f.value

    summary = _section_by_role(root, "summary")
    if (summary and summary.visible and summary.children
            and isinstance(summary.children[0], FieldNode)
            and summary.children[0].visible):
        out["hero"] = summary.children[0].value

    skills = _section_by_role(root, "skills")
    if (skills and skills.visible and skills.children
            and isinstance(skills.children[0], FieldNode)
            and skills.children[0].visible):
        out["skills"] = list(skills.children[0].value)

    def _rows(role: str) -> list[dict]:
        sect = _section_by_role(root, role)
        if (not sect or not sect.visible or not sect.children
                or not isinstance(sect.children[0], ListNode)):
            return []
        return [
            {f.key: f.value for f in item.children}
            for item in sect.children[0].children
            if item.visible
        ]

    out["work_history"] = [
        {
            "company": r.get("company", ""),
            "title": r.get("title", ""),
            "start": r.get("start", ""),
            "end": r.get("end", ""),
            "summary": r.get("summary", ""),
        }
        for r in _rows("experience")
    ]
    out["education"] = [
        {
            "institution": r.get("institution", ""),
            "degree": r.get("degree", ""),
            "field": r.get("field", ""),
            "graduated": r.get("graduated", ""),
            "gpa": _gpa_to_float(r.get("gpa", "")),
        }
        for r in _rows("education")
    ]
    out["projects"] = [
        {
            "name": r.get("name", ""),
            "description": r.get("description", ""),
            "url": r.get("url", ""),
            "technologies": list(r.get("technologies", [])),
        }
        for r in _rows("projects")
    ]
    return out


def _field_value_str(field: FieldNode) -> str:
    """Render a field value for prompt injection.

    Args:
        field: The field whose value to render.

    Returns:
        A string representation of the field value. Lists are joined with ", ".
    """
    if isinstance(field.value, list):
        return ", ".join(str(v) for v in field.value)
    return "" if field.value is None else str(field.value)


def _entry_label(group: GroupNode) -> str:
    """An entry's display name, falling back to its first non-empty field value."""
    if group.name.strip():
        return group.name.strip()
    for f in group.children:
        s = _field_value_str(f).strip()
        if s:
            return s
    return "Entry"


def build_section_prompt(section: SectionNode) -> str:
    """Assemble a section's authoring prompt, nesting unlocked list-entry prompts.

    Produces ``[<SectionName>: <section.prompt> [<ItemName>: <item.prompt>] …]``.
    Empty section/item prompts are omitted; a locked section returns ``""`` (it is
    never authored); locked entries are skipped. Returns ``""`` when neither the
    section prompt nor any item prompt is present.

    Args:
        section: The section to assemble a prompt for.

    Returns:
        The folded prompt string, or ``""`` when nothing is authored.
    """
    if section.locked:
        return ""
    parts: list[str] = []
    if section.prompt.strip():
        parts.append(section.prompt.strip())
    child = section.children[0] if section.children else None
    if isinstance(child, ListNode):
        for entry in child.children:
            if entry.locked or not entry.prompt.strip():
                continue
            parts.append(f"[{_entry_label(entry)}: {entry.prompt.strip()}]")
    if not parts:
        return ""
    return f"[{section.name}: {' '.join(parts)}]"


def _collect_fields(node: object) -> list[FieldNode]:
    """All FieldNodes anywhere under ``node`` (groups, list entries, bare).

    The item_template of a list is intentionally not traversed.

    Args:
        node: The node to extract fields from.

    Returns:
        A list of all FieldNode instances found in the node's tree.
    """
    out: list[FieldNode] = []

    def walk(n: object) -> None:
        if isinstance(n, FieldNode):
            out.append(n)
            return
        for c in getattr(n, "children", None) or []:
            walk(c)

    walk(node)
    return out


def _node_by_id(root: "RootNode", node_id: str) -> object | None:
    """Return the first node whose ``id`` matches, searching the whole tree.

    Args:
        root: The root of the tree to search.
        node_id: The id to search for.

    Returns:
        The first node with matching id, or None if not found.
    """
    found: object | None = None

    def walk(n: object) -> None:
        nonlocal found
        if found is not None:
            return
        if getattr(n, "id", None) == node_id:
            found = n
            return
        for c in getattr(n, "children", None) or []:
            walk(c)
        if isinstance(n, ListNode):
            # item_template is structural; do not match against it.
            return

    walk(root)
    return found


def resolve_profile_tokens(root: "RootNode", text: str) -> str:
    """Substitute ``{profile:<nodeId>}`` tokens with the node's rendered value.

    A field node id resolves to that field's value; a section/group/list node id
    resolves to ``"<name>: <value>"`` lines for every field under it. Unknown ids
    are left untouched.

    Args:
        root: The profile tree.
        text: A prompt string possibly containing ``{profile:<id>}`` tokens.

    Returns:
        ``text`` with recognized profile tokens substituted.
    """

    def _replace(m: "re.Match[str]") -> str:
        node = _node_by_id(root, m.group(1))
        if node is None:
            return m.group(0)
        if isinstance(node, FieldNode):
            return _field_value_str(node)
        lines = [f"{f.name}: {_field_value_str(f)}" for f in _collect_fields(node)]
        return "\n".join(lines)

    return re.sub(r"\{profile:([\w-]+)\}", _replace, text)
