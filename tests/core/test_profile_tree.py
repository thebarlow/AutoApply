from __future__ import annotations

import pytest


def test_field_text_value_coerces_to_str():
    from core.profile_tree import FieldNode

    f = FieldNode(name="Email", key="email", kind="text", value="a@b.com")
    assert f.value == "a@b.com"
    assert isinstance(f.id, str) and f.id


def test_field_taglist_value_coerces_to_list():
    from core.profile_tree import FieldNode

    f = FieldNode(name="Skills", key="skills", kind="taglist", value=["Python", "SQL"])
    assert f.value == ["Python", "SQL"]


def test_field_text_given_none_becomes_empty_string():
    from core.profile_tree import FieldNode

    f = FieldNode(name="Phone", key="phone", kind="text", value=None)
    assert f.value == ""


def test_nested_tree_builds():
    from core.profile_tree import FieldNode, GroupNode, ListNode, RootNode, SectionNode

    item = GroupNode(
        name="item",
        children=[FieldNode(name="Company", key="company", kind="text")],
    )
    sect = SectionNode(
        name="Experience",
        role="experience",
        children=[ListNode(name="Experience", item_template=item, children=[])],
    )
    root = RootNode(children=[sect])
    assert root.children[0].children[0].item_template.children[0].key == "company"
