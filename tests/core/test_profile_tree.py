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


def _experience_section():
    from core.profile_tree import FieldNode, GroupNode, ListNode, SectionNode

    tmpl = GroupNode(
        name="item",
        children=[
            FieldNode(name="Company", key="company", kind="text"),
            FieldNode(name="Title", key="title", kind="text"),
        ],
    )
    inst = GroupNode(
        name="item",
        children=[
            FieldNode(name="Company", key="company", kind="text", value="Acme"),
            FieldNode(name="Title", key="title", kind="text", value="SWE"),
        ],
    )
    return SectionNode(
        name="Experience",
        role="experience",
        children=[ListNode(name="Experience", item_template=tmpl, children=[inst])],
    )


def test_validate_accepts_conforming_tree():
    from core.profile_tree import RootNode, validate_tree

    validate_tree(RootNode(children=[_experience_section()]))  # no raise


def test_validate_rejects_nonconforming_list_item():
    from core.profile_tree import (
        FieldNode,
        GroupNode,
        ListNode,
        RootNode,
        SectionNode,
        TreeValidationError,
        validate_tree,
    )

    tmpl = GroupNode(children=[FieldNode(name="Company", key="company", kind="text")])
    bad = GroupNode(children=[FieldNode(name="Other", key="other", kind="text")])
    root = RootNode(
        children=[
            SectionNode(
                name="Experience",
                role="experience",
                children=[ListNode(item_template=tmpl, children=[bad])],
            )
        ]
    )
    with pytest.raises(TreeValidationError):
        validate_tree(root)


def test_validate_rejects_duplicate_sibling_order():
    from core.profile_tree import (
        RootNode,
        SectionNode,
        TreeValidationError,
        validate_tree,
    )

    root = RootNode(
        children=[
            SectionNode(name="A", order=0, children=[]),
            SectionNode(name="B", order=0, children=[]),
        ]
    )
    with pytest.raises(TreeValidationError):
        validate_tree(root)


def test_validate_rejects_section_with_two_children():
    from core.profile_tree import (
        FieldNode,
        RootNode,
        SectionNode,
        TreeValidationError,
        validate_tree,
    )

    root = RootNode(
        children=[
            SectionNode(
                name="X",
                children=[
                    FieldNode(name="a", key="a", kind="text"),
                    FieldNode(name="b", key="b", kind="text"),
                ],
            )
        ]
    )
    with pytest.raises(TreeValidationError):
        validate_tree(root)


def test_validate_rejects_invalid_bullets_bounds():
    from core.profile_tree import (
        FieldNode,
        RootNode,
        SectionNode,
        TreeValidationError,
        validate_tree,
    )

    root = RootNode(
        children=[
            SectionNode(
                name="S",
                children=[
                    FieldNode(name="B", key="b", kind="bullets", min=5, max=2),
                ],
            )
        ]
    )
    with pytest.raises(TreeValidationError):
        validate_tree(root)


def test_validate_rejects_duplicate_group_key():
    from core.profile_tree import (
        FieldNode,
        GroupNode,
        RootNode,
        SectionNode,
        TreeValidationError,
        validate_tree,
    )

    root = RootNode(
        children=[
            SectionNode(
                name="S",
                children=[
                    GroupNode(
                        name="g",
                        children=[
                            FieldNode(name="A", key="x", kind="text"),
                            FieldNode(name="B", key="x", kind="text"),
                        ],
                    )
                ],
            )
        ]
    )
    with pytest.raises(TreeValidationError):
        validate_tree(root)


LEGACY = {
    "first_name": "Matt",
    "last_name": "Barlow",
    "hero": "Engineer",
    "email": "m@x.com",
    "phone": "555",
    "location": "Remote",
    "github": "gh",
    "linkedin": "li",
    "website": "w",
    "skills": ["Python", "SQL"],
    "work_history": [
        {
            "company": "Acme",
            "title": "SWE",
            "start": "2022",
            "end": "Now",
            "summary": "Built.",
        },
    ],
    "education": [
        {
            "institution": "Columbia",
            "degree": "B.S.",
            "field": "EE",
            "graduated": "2018",
            "gpa": 3.5,
        },
    ],
    "projects": [
        {
            "name": "auto_apply",
            "description": "Pipeline",
            "url": "u",
            "technologies": ["Python"],
        },
    ],
}


def test_legacy_to_tree_is_valid_and_has_sections():
    from core.profile_tree import legacy_to_tree, validate_tree

    root = legacy_to_tree(LEGACY)
    validate_tree(root)
    roles = [s.role for s in root.children]
    assert roles == [
        "header",
        "summary",
        "experience",
        "education",
        "projects",
        "skills",
    ]


def test_legacy_to_tree_populates_experience_item():
    from core.profile_tree import legacy_to_tree

    root = legacy_to_tree(LEGACY)
    exp = next(s for s in root.children if s.role == "experience")
    item = exp.children[0].children[0]
    vals = {f.key: f.value for f in item.children}
    assert vals["company"] == "Acme" and vals["summary"] == "Built."
