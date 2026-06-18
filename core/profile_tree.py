"""Recursive, typed profile/résumé tree: closed node vocabulary.

Pure module — no DB, no LLM. Provides ``FieldNode``, ``GroupNode``,
``ListNode``, ``SectionNode``, and ``RootNode`` — the complete vocabulary for
representing a structured profile/résumé tree.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator


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
    regen_lock: bool = False
    children: list[FieldNode] = Field(default_factory=list)


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
            if (
                node.min is not None
                and node.max is not None
                and not (0 <= node.min <= node.max)
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
    validate_tree(root)
    return root


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
    if header and header.children and isinstance(header.children[0], GroupNode):
        for f in header.children[0].children:
            if f.key in out:
                out[f.key] = f.value

    summary = _section_by_role(root, "summary")
    if summary and summary.children and isinstance(summary.children[0], FieldNode):
        out["hero"] = summary.children[0].value

    skills = _section_by_role(root, "skills")
    if skills and skills.children and isinstance(skills.children[0], FieldNode):
        out["skills"] = list(skills.children[0].value)

    def _rows(role: str) -> list[dict]:
        sect = _section_by_role(root, role)
        if not sect or not sect.children or not isinstance(sect.children[0], ListNode):
            return []
        return [
            {f.key: f.value for f in item.children}
            for item in sect.children[0].children
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
