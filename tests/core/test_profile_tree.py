from __future__ import annotations

import pytest

from core.profile_tree import RootNode


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


def test_merge_flat_into_stored_reflects_flat_edits():
    from core.profile_tree import RootNode, merge_flat_into_stored, tree_to_legacy

    data = merge_flat_into_stored({}, dict(LEGACY))  # store an initial tree
    data["email"] = "edited@x.com"  # edit a flat field; tree now stale
    data = merge_flat_into_stored(data, data)  # overlay onto existing tree
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


def _tree_with_custom_and_lock():
    """A migrated tree plus a custom section and a locked experience item."""
    from core.profile_tree import FieldNode, GroupNode, ListNode, SectionNode, legacy_to_tree

    tree = legacy_to_tree(LEGACY)  # header/summary/experience/education/projects/skills
    # lock the first experience item (GroupNode uses locked, not regen_lock)
    exp = next(s for s in tree.children if s.role == "experience")
    exp.children[0].children[0].locked = True
    # add a custom (role=None) section with a single text field
    tree.children.append(
        SectionNode(
            name="Awards", role=None, order=99,
            children=[GroupNode(name="Awards", children=[
                FieldNode(name="Award", key="award", kind="text", value="Hackathon Winner"),
            ])],
        )
    )
    return tree


def test_apply_flat_overlay_updates_scalar_preserving_id():
    from core.profile_tree import apply_flat_to_tree, _section_by_role, legacy_to_tree

    tree = legacy_to_tree(LEGACY)
    email_field = _section_by_role(tree, "header").children[0].children
    target = next(f for f in email_field if f.key == "email")
    original_id = target.id
    apply_flat_to_tree(tree, {"email": "new@x.com"})
    target = next(f for f in _section_by_role(tree, "header").children[0].children if f.key == "email")
    assert target.value == "new@x.com"
    assert target.id == original_id  # id preserved


def test_apply_flat_overlay_list_update_append_truncate():
    from core.profile_tree import apply_flat_to_tree, _section_by_role, legacy_to_tree

    tree = legacy_to_tree(LEGACY)  # 1 work_history entry
    exp_list = _section_by_role(tree, "experience").children[0]
    first_item_id = exp_list.children[0].id

    # 2 rows: update existing + append one
    apply_flat_to_tree(tree, {"work_history": [
        {"company": "Acme2", "title": "SWE", "start": "2022", "end": "Now", "summary": "Updated."},
        {"company": "NewCo", "title": "Lead", "start": "2024", "end": "Now", "summary": "Led."},
    ]})
    assert len(exp_list.children) == 2
    assert exp_list.children[0].id == first_item_id  # preserved
    vals0 = {f.key: f.value for f in exp_list.children[0].children}
    assert vals0["company"] == "Acme2"

    # back to 0 rows: truncate
    apply_flat_to_tree(tree, {"work_history": []})
    assert len(exp_list.children) == 0


def test_apply_flat_overlay_preserves_custom_section_and_lock():
    from core.profile_tree import apply_flat_to_tree, _section_by_role

    tree = _tree_with_custom_and_lock()
    apply_flat_to_tree(tree, {"skills": ["Rust"], "work_history": [
        {"company": "Acme", "title": "SWE", "start": "2022", "end": "Now", "summary": "x"},
    ]})
    # custom section survived
    awards = next((s for s in tree.children if s.role is None and s.name == "Awards"), None)
    assert awards is not None
    assert awards.children[0].children[0].value == "Hackathon Winner"
    # lock survived
    exp = _section_by_role(tree, "experience")
    assert exp.children[0].children[0].locked is True


def test_apply_flat_overlay_education_gpa_coerced_to_str():
    from core.profile_tree import apply_flat_to_tree, _section_by_role, legacy_to_tree

    tree = legacy_to_tree(LEGACY)
    apply_flat_to_tree(tree, {"education": [
        {"institution": "MIT", "degree": "B.S.", "field": "CS", "graduated": "2020", "gpa": 4.0},
    ]})
    item = _section_by_role(tree, "education").children[0].children[0]
    gpa = next(f.value for f in item.children if f.key == "gpa")
    assert gpa == "4.0" and isinstance(gpa, str)


def test_section_and_group_have_lock_and_prompt_defaults():
    from core.profile_tree import GroupNode, SectionNode

    s = SectionNode(name="X")
    assert s.locked is False and s.prompt == ""
    g = GroupNode(name="G")
    assert g.locked is False and g.prompt == ""


def test_group_legacy_regen_lock_migrates_to_locked():
    from core.profile_tree import GroupNode

    g = GroupNode.model_validate({"type": "group", "name": "G", "regen_lock": True})
    assert g.locked is True


def test_group_explicit_locked_wins_over_legacy_regen_lock():
    from core.profile_tree import GroupNode

    g = GroupNode.model_validate(
        {"type": "group", "name": "G", "regen_lock": True, "locked": False}
    )
    assert g.locked is False


def test_tree_with_locks_and_prompts_validates():
    from core.profile_tree import GroupNode, RootNode, SectionNode, validate_tree

    root = RootNode(
        children=[
            SectionNode(
                name="S",
                order=0,
                locked=True,
                prompt="Tailor S",
                children=[GroupNode(name="G", locked=True, prompt="Tailor G")],
            ),
        ]
    )
    validate_tree(root)  # must not raise


def _sample_root():
    from core.profile_tree import FieldNode, GroupNode, SectionNode

    return RootNode(children=[
        SectionNode(name="Skills", role="skills", order=0, children=[
            FieldNode(name="Technical", key="skills", kind="taglist",
                      value=["Python", "Go"])]),
        SectionNode(name="My Awards", role=None, order=1, children=[
            GroupNode(name="Awards", children=[
                FieldNode(name="Award", key="award", kind="text", value="Winner")])]),
    ])


def test_resolve_field_token_by_id():
    from core.profile_tree import FieldNode, SectionNode, resolve_profile_tokens

    f = FieldNode(
        name="Tech", key="skills", kind="taglist", value=["Python", "Go"]
    )
    root = RootNode(
        children=[SectionNode(name="Skills", role="skills", order=0, children=[f])]
    )
    assert resolve_profile_tokens(root, "Have: {profile:%s}" % f.id) == "Have: Python, Go"


def test_resolve_section_token_by_id_joins_fields():
    from core.profile_tree import FieldNode, GroupNode, SectionNode, resolve_profile_tokens

    sec = SectionNode(
        name="Awards",
        role=None,
        order=0,
        children=[
            GroupNode(
                name="Awards",
                children=[FieldNode(name="Award", key="award", kind="text", value="Winner")],
            )
        ],
    )
    root = RootNode(children=[sec])
    out = resolve_profile_tokens(root, "{profile:%s}" % sec.id)
    assert "Award: Winner" in out


def test_resolve_unknown_id_left_as_is():
    from core.profile_tree import FieldNode, SectionNode, resolve_profile_tokens

    root = RootNode(
        children=[
            SectionNode(
                name="S",
                order=0,
                children=[FieldNode(name="A", key="a", kind="text", value="x")],
            )
        ]
    )
    assert (
        resolve_profile_tokens(root, "{profile:nope} {job.title}")
        == "{profile:nope} {job.title}"
    )


class _StubDB:
    def query(self, *a, **k):
        return self

    def filter_by(self, *a, **k):
        return self

    def first(self):
        return None
