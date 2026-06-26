from __future__ import annotations

from core.profile_tree import FieldNode, GroupNode, ListNode, SectionNode
from core.tree_assembler import _experience_section_md, _render_body


def _exp(summary_value, kind):
    entry = GroupNode(name="Experience Item", children=[
        FieldNode(name="Title", key="title", kind="text", value="Engineer"),
        FieldNode(name="Company", key="company", kind="text", value="Acme"),
        FieldNode(name="Summary", key="summary", kind=kind, value=summary_value),
    ])
    return SectionNode(name="Experience", role="experience", children=[
        ListNode(name="Experience", item_template=entry.model_copy(deep=True), children=[entry]),
    ])


def test_render_body_list_becomes_bullets():
    assert _render_body(["did A", "did B"]) == "- did A\n- did B"


def test_render_body_string_is_prose():
    assert _render_body("Led a team.") == "Led a team."


def test_experience_renders_bullets_for_list_value():
    md = _experience_section_md(_exp(["shipped X", "owned Y"], "bullets"))
    assert "- shipped X" in md and "- owned Y" in md
    assert "### Engineer, Acme" in md


def test_experience_renders_paragraph_for_string_value():
    md = _experience_section_md(_exp("Led a cross-functional team.", "markdown"))
    assert "Led a cross-functional team." in md
    assert "- Led" not in md
