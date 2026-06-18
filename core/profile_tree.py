"""Recursive, typed profile/résumé tree: closed node vocabulary.

Pure module — no DB, no LLM. Provides ``FieldNode``, ``GroupNode``,
``ListNode``, ``SectionNode``, and ``RootNode`` — the complete vocabulary for
representing a structured profile/résumé tree.
"""

from __future__ import annotations

import uuid
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
