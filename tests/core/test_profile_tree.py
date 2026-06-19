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


@pytest.mark.parametrize(
    "v,expected",
    [(3.5, "3.5"), (4.0, "4.0"), (None, ""), ("", ""), (0.0, "0.0"), (3, "3")],
)
def test_gpa_to_str(v, expected):
    from core.profile_tree import _gpa_to_str

    assert _gpa_to_str(v) == expected


def test_legacy_to_tree_populates_experience_item():
    from core.profile_tree import legacy_to_tree

    root = legacy_to_tree(LEGACY)
    exp = next(s for s in root.children if s.role == "experience")
    item = exp.children[0].children[0]
    vals = {f.key: f.value for f in item.children}
    assert vals["company"] == "Acme" and vals["summary"] == "Built."


def test_tree_to_legacy_round_trips_fields():
    from core.profile_tree import legacy_to_tree, tree_to_legacy

    out = tree_to_legacy(legacy_to_tree(LEGACY))
    assert out["email"] == "m@x.com"
    assert out["skills"] == ["Python", "SQL"]
    assert out["work_history"][0] == {
        "company": "Acme",
        "title": "SWE",
        "start": "2022",
        "end": "Now",
        "summary": "Built.",
    }
    assert out["education"][0]["gpa"] == 3.5
    assert out["projects"][0]["technologies"] == ["Python"]


def test_golden_round_trip_markdown_identical():
    """legacy -> tree -> legacy must produce byte-identical assembled markdown."""
    from types import SimpleNamespace

    from core.document_assembler import assemble_resume_markdown
    from core.document_builder import build_resume_document
    from core.profile_tree import legacy_to_tree, tree_to_legacy
    from core.schemas import ResumeGeneration
    from core.user import EducationEntry, ProjectEntry, WorkHistoryEntry

    def _user(d: dict):
        u = SimpleNamespace(
            **{
                k: ""
                for k in (
                    "first_name",
                    "last_name",
                    "email",
                    "phone",
                    "location",
                    "github",
                    "linkedin",
                    "website",
                )
            }
        )
        u.first_name = d["first_name"]
        u.last_name = d["last_name"]
        u.email = d["email"]
        u.phone = d["phone"]
        u.location = d["location"]
        u.github = d["github"]
        u.linkedin = d["linkedin"]
        u.website = d["website"]
        u.skills = d["skills"]
        u.work_history = [WorkHistoryEntry(**e) for e in d["work_history"]]
        u.education = [EducationEntry(**e) for e in d["education"]]
        u.projects = [ProjectEntry(**e) for e in d["projects"]]
        u.full_name = lambda: f"{d['first_name']} {d['last_name']}".strip()
        return u

    gen = ResumeGeneration()  # empty prose; structure-only comparison
    before = assemble_resume_markdown(
        build_resume_document(_user(LEGACY), gen, _StubDB())
    )
    after_legacy = tree_to_legacy(legacy_to_tree(LEGACY))
    after = assemble_resume_markdown(
        build_resume_document(_user(after_legacy), gen, _StubDB())
    )
    assert before == after


def test_with_rebuilt_tree_reflects_flat_edits():
    from core.profile_tree import RootNode, tree_to_legacy, with_rebuilt_tree

    data = with_rebuilt_tree(dict(LEGACY))  # store an initial tree
    data["email"] = "edited@x.com"  # edit a flat field; tree now stale
    data = with_rebuilt_tree(data)  # rebuild from the edited flat fields
    derived = tree_to_legacy(RootNode.model_validate(data["profile_tree"]))
    assert derived["email"] == "edited@x.com"


def test_integer_gpa_round_trips():
    from core.profile_tree import legacy_to_tree, tree_to_legacy

    data = {
        "education": [
            {
                "institution": "X",
                "degree": "B.S.",
                "field": "EE",
                "graduated": "2018",
                "gpa": 3,
            }
        ]
    }
    out = tree_to_legacy(legacy_to_tree(data))
    assert out["education"][0]["gpa"] == 3.0


class _StubDB:
    def query(self, *a, **k):
        return self

    def filter_by(self, *a, **k):
        return self

    def first(self):
        return None
