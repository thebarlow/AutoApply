import json

from core.profile_tree import FieldNode, GroupNode, RootNode, SectionNode
from core.resume_document_io import (
    SCHEMA_TREE_V1,
    deserialize_document_tree,
    is_tree_v1,
    resolve_schema,
    serialize_document_tree,
)


def _tree() -> RootNode:
    return RootNode(children=[
        SectionNode(name="Header", role="header", order=0, children=[
            GroupNode(name="Contact", children=[
                FieldNode(name="Email", key="email", kind="text", value="a@b.co"),
            ]),
        ]),
    ])


def test_serialize_injects_schema_key():
    raw = serialize_document_tree(_tree())
    assert json.loads(raw)["schema"] == SCHEMA_TREE_V1


def test_resolve_schema_reads_value():
    assert resolve_schema(serialize_document_tree(_tree())) == "tree-v1"


def test_resolve_schema_absent_is_none():
    assert resolve_schema('{"type": "root", "children": []}') is None


def test_resolve_schema_unparseable_is_none():
    assert resolve_schema("not json") is None


def test_is_tree_v1():
    assert is_tree_v1(serialize_document_tree(_tree())) is True
    assert is_tree_v1('{"type":"root","children":[]}') is False


def test_roundtrip_preserves_tree():
    root = _tree()
    back = deserialize_document_tree(serialize_document_tree(root))
    assert back.model_dump() == root.model_dump()


def test_roundtrip_preserves_locked_and_custom_section():
    root = RootNode(children=[
        SectionNode(name="Patents", order=0, locked=True, children=[
            GroupNode(name="g", children=[
                FieldNode(name="Title", key="title", kind="text", value="X"),
            ]),
        ]),
    ])
    back = deserialize_document_tree(serialize_document_tree(root))
    assert back.model_dump() == root.model_dump()
    assert back.children[0].locked is True
