from core.schemas import ExtraSection, ParsedEntry, ParsedField, ParseResponse
from core.parsed_sections import (
    build_section_from_parsed, merge_section,
    builtin_sections_from_parse, set_section_customize, iter_leaf_fields, _item_name,
)
from core.profile_tree import RootNode, validate_tree


def _parsed(**kw):
    base = {"first_name": "A", "last_name": "B"}
    base.update(kw)
    return ParseResponse.model_validate(base)


def test_empty_sections_are_dropped():
    parsed = _parsed(skills=[], work_history=[], education=[], projects=[])
    roles = {s.role for s in builtin_sections_from_parse(parsed)}
    assert "skills" not in roles
    assert "experience" not in roles


def test_heading_overrides_section_name():
    parsed = _parsed(
        work_history=[{"company": "Acme", "title": "Eng", "start": "", "end": "", "summary": ""}],
        work_history_heading="Employment History",
    )
    exp = next(s for s in builtin_sections_from_parse(parsed) if s.role == "experience")
    assert exp.name == "Employment History"


def test_header_omits_empty_fields():
    parsed = _parsed(email="a@b.com")  # no github
    header = next(s for s in builtin_sections_from_parse(parsed) if s.role == "header")
    field_keys = {f.key for f in header.children[0].children}
    assert "email" in field_keys
    assert "github" not in field_keys


def test_experience_item_best_guess_name():
    parsed = _parsed(work_history=[{"company": "Acme", "title": "Eng", "start": "", "end": "", "summary": ""}])
    exp = next(s for s in builtin_sections_from_parse(parsed) if s.role == "experience")
    item = exp.children[0].children[0]  # ListNode -> first GroupNode
    assert item.name == "Acme — Eng"


def test_item_name_falls_back():
    assert _item_name("experience", {"company": "", "title": ""}) == "Experience Item"


def test_set_section_customize_flips_writable_fields():
    parsed = _parsed(work_history=[{"company": "Acme", "title": "Eng", "start": "", "end": "", "summary": "x"}])
    exp = next(s for s in builtin_sections_from_parse(parsed) if s.role == "experience")
    set_section_customize(exp, True, "Tailor it")
    writable = [f for f in iter_leaf_fields(exp) if f.kind in {"markdown", "bullets", "taglist"}]
    assert all(f.llm_output for f in writable)
    assert exp.prompt == "Tailor it"
    set_section_customize(exp, False, "")
    assert all(not f.llm_output for f in iter_leaf_fields(exp))
    assert exp.prompt == ""


def test_multi_entry_list_section_has_unique_item_orders():
    """A novel 'list' section with 2+ entries must pass validate_tree.

    Regression: item GroupNodes previously all defaulted to order=0, which
    tripped validate_tree's duplicate-sibling-order check and 422'd parse/apply
    (e.g. a CERTIFICATIONS section with multiple rows).
    """
    certs = ExtraSection(name="CERTIFICATIONS", kind="list", entries=[
        ParsedEntry(fields=[ParsedField(label="Name", value="AWS Cloud Practitioner")]),
        ParsedEntry(fields=[ParsedField(label="Name", value="ITIL Foundation")]),
    ])
    section = build_section_from_parsed(certs)
    lst = section.children[0]
    assert [c.order for c in lst.children] == [0, 1]
    root = RootNode()
    root.children.append(section)
    validate_tree(root)  # must not raise


def test_merge_list_sections_reindexes_item_orders():
    """Merging two list sections must not collide sibling orders.

    Regression: both lists number items from 0, so a raw extend produced a
    duplicate order that tripped validate_tree and 422'd the merge action.
    """
    def _certs(*names):
        return ExtraSection(name="CERTS", kind="list", entries=[
            ParsedEntry(fields=[ParsedField(label="Name", value=n)]) for n in names
        ])

    existing = build_section_from_parsed(_certs("A", "B"))
    incoming = build_section_from_parsed(_certs("C"))
    merge_section(existing, incoming)
    lst = existing.children[0]
    assert [c.order for c in lst.children] == [0, 1, 2]
    root = RootNode()
    root.children.append(existing)
    validate_tree(root)  # must not raise
