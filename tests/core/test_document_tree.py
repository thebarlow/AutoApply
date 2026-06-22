"""Tests for the document-tree builder (Profile Schema Engine #4A)."""
from __future__ import annotations

from core.document_tree import build_resume_document_tree
from core.profile_tree import (
    FieldNode, GroupNode, ListNode, RootNode, SectionNode,
)


def _summary_section(text: str = "", visible: bool = True) -> SectionNode:
    return SectionNode(
        name="Summary", role="summary", order=1, visible=visible,
        children=[FieldNode(
            name="Summary", key="hero", kind="markdown", order=0,
            llm_output=True, value=text,
        )],
    )


def test_bakes_authored_value_by_field_id():
    sec = _summary_section("OLD")
    fid = sec.children[0].id
    out = build_resume_document_tree(RootNode(children=[sec]), {fid: "NEW"})
    assert out.children[0].children[0].value == "NEW"


def test_input_tree_is_not_mutated():
    sec = _summary_section("OLD")
    fid = sec.children[0].id
    root = RootNode(children=[sec])
    build_resume_document_tree(root, {fid: "NEW"})
    assert root.children[0].children[0].value == "OLD"  # original untouched


def test_drops_invisible_section():
    visible = _summary_section("keep")
    hidden = SectionNode(
        name="Secret", role=None, order=2, visible=False,
        children=[GroupNode(children=[FieldNode(name="X", key="x", value="hide")])],
    )
    out = build_resume_document_tree(RootNode(children=[visible, hidden]), {})
    assert [s.name for s in out.children] == ["Summary"]


def test_drops_invisible_list_entry():
    lst = ListNode(name="Experience", item_template=GroupNode(), children=[
        GroupNode(visible=True, children=[FieldNode(name="Co", key="company", value="A")]),
        GroupNode(visible=False, children=[FieldNode(name="Co", key="company", value="B")]),
    ])
    sec = SectionNode(name="Experience", role="experience", order=0, children=[lst])
    out = build_resume_document_tree(RootNode(children=[sec]), {})
    kept = out.children[0].children[0].children
    assert len(kept) == 1
    assert kept[0].children[0].value == "A"


def test_drops_context_only_field():
    grp = GroupNode(children=[
        FieldNode(name="Anchor", key="anchor", llm_input=True, llm_output=False, value="ctx"),
        FieldNode(name="Body", key="body", kind="markdown", llm_output=True, value="real"),
    ])
    sec = SectionNode(name="Custom", role=None, order=0, children=[grp])
    out = build_resume_document_tree(RootNode(children=[sec]), {})
    keys = [f.key for f in out.children[0].children[0].children]
    assert keys == ["body"]


def test_keeps_locked_entry_verbatim():
    locked = GroupNode(locked=True, children=[
        FieldNode(name="Co", key="company", value="Fixed"),
        FieldNode(name="Sum", key="summary", kind="markdown", llm_output=True, value="orig"),
    ])
    fid = locked.children[1].id
    lst = ListNode(name="Experience", item_template=GroupNode(), children=[locked])
    sec = SectionNode(name="Experience", role="experience", order=0, children=[lst])
    # Even if authored somehow references it, the builder bakes by id; section_generator
    # never authors locked entries, so authored is empty here — value stays "orig".
    out = build_resume_document_tree(RootNode(children=[sec]), {})
    kept = out.children[0].children[0].children[0]
    assert kept.locked is True
    assert kept.children[1].value == "orig"


def test_drops_section_with_invisible_bare_field():
    sec = _summary_section("x", visible=True)
    sec.children[0].visible = False
    out = build_resume_document_tree(RootNode(children=[sec]), {})
    assert out.children == []
