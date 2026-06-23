"""Serialize/deserialize a résumé *document tree* with a schema discriminator.

The ``documents.structured_json`` column stores either a legacy ``ResumeDocument``
(no ``schema`` key) or a tree-v1 document tree (a ``RootNode`` JSON with a
top-level ``"schema": "tree-v1"`` key). Every read path uses ``resolve_schema`` /
``is_tree_v1`` to branch. Pure module — no DB, no LLM, no filesystem.
"""
from __future__ import annotations

import json

from core.profile_tree import RootNode

SCHEMA_TREE_V1 = "tree-v1"


def serialize_document_tree(root: RootNode) -> str:
    """JSON for a document tree, with the ``schema`` discriminator added."""
    data = json.loads(root.model_dump_json())
    data["schema"] = SCHEMA_TREE_V1
    return json.dumps(data)


def resolve_schema(raw: str) -> str | None:
    """The stored ``schema`` value, or ``None`` if absent/unparseable."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    value = data.get("schema")
    return value if isinstance(value, str) else None


def is_tree_v1(raw: str) -> bool:
    """True iff ``raw`` is a tree-v1 document tree."""
    return resolve_schema(raw) == SCHEMA_TREE_V1


def deserialize_document_tree(raw: str) -> RootNode:
    """Parse a tree-v1 JSON string back into a ``RootNode`` (ignores ``schema``)."""
    data = json.loads(raw)
    data.pop("schema", None)
    return RootNode.model_validate(data)
