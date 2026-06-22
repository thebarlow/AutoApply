"""Tests for the document-tree Markdown assembler (Profile Schema Engine #4A)."""
from __future__ import annotations

from core.profile_tree import (
    FieldNode, GroupNode, ListNode, RootNode, SectionNode,
)
from core.tree_assembler import assemble_resume_tree_markdown


def _custom_list_section() -> SectionNode:
    entry = GroupNode(children=[
        FieldNode(name="Org", key="org", kind="text", value="Red Cross"),
        FieldNode(name="Detail", key="detail", kind="markdown", value="Helped at shelters."),
    ])
    return SectionNode(
        name="Volunteering", role=None, order=10,
        children=[ListNode(name="Volunteering", item_template=GroupNode(), children=[entry])],
    )


def test_custom_section_renders_generically():
    md = assemble_resume_tree_markdown(RootNode(children=[_custom_list_section()]))
    assert md == (
        "## Volunteering\n\n"
        "**Org:** Red Cross\n\n"
        "Helped at shelters.\n"
    )


def test_taglist_field_renders_inline():
    sec = SectionNode(name="Tools", role=None, order=0, children=[
        GroupNode(children=[FieldNode(name="Tools", key="tools", kind="taglist",
                                      value=["Git", "Docker"])]),
    ])
    md = assemble_resume_tree_markdown(RootNode(children=[sec]))
    assert md == "## Tools\n\n**Tools:** Git, Docker\n"


def test_bullets_field_renders_as_list():
    sec = SectionNode(name="Highlights", role=None, order=0, children=[
        GroupNode(children=[FieldNode(name="Points", key="points", kind="bullets",
                                      value=["First", "Second"])]),
    ])
    md = assemble_resume_tree_markdown(RootNode(children=[sec]))
    assert md == "## Highlights\n\n- First\n- Second\n"


def test_empty_section_is_omitted():
    empty = SectionNode(name="Blank", role=None, order=0, children=[
        GroupNode(children=[FieldNode(name="X", key="x", kind="text", value="")]),
    ])
    keep = _custom_list_section()
    md = assemble_resume_tree_markdown(RootNode(children=[empty, keep]))
    assert md.startswith("## Volunteering")
    assert "Blank" not in md


def test_invisible_section_skipped():
    hidden = _custom_list_section()
    hidden.visible = False
    md = assemble_resume_tree_markdown(RootNode(children=[hidden]))
    assert md.strip() == ""
