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
