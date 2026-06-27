import pytest

from core.profile_tree import RootNode
from core.schemas import ParseResponse, ExtraSection, ParsedField, ParsedEntry
from core.parsed_sections import (
    build_section_from_parsed, builtin_sections_from_parse,
    find_section, add_section, replace_section, merge_section,
)


def _root_with(*sections) -> RootNode:
    return RootNode(children=list(sections))


def test_builtin_sections_have_roles():
    parsed = ParseResponse(first_name="Ada", skills=["Python"],
                           work_history=[{"company": "Acme", "title": "Eng"}])
    roles = {s.role for s in builtin_sections_from_parse(parsed)}
    assert {"skills", "experience"} <= roles


def test_add_and_find():
    root = _root_with()
    sec = build_section_from_parsed(ExtraSection(name="Awards", kind="bullets", items=["x"]))
    add_section(root, sec)
    assert find_section(root, name="awards") is not None


def test_replace_keeps_id():
    sec = build_section_from_parsed(ExtraSection(name="About", kind="markdown", markdown="old"))
    root = _root_with(sec)
    sid = sec.id
    incoming = build_section_from_parsed(ExtraSection(name="About", kind="markdown", markdown="new"))
    replace_section(sec, incoming)
    assert sec.id == sid and sec.children[0].value == "new"


def test_merge_taglist_unions_case_insensitive():
    sec = build_section_from_parsed(ExtraSection(name="Skills", kind="taglist", items=["Python", "Go"]))
    incoming = build_section_from_parsed(ExtraSection(name="Skills", kind="taglist", items=["go", "Rust"]))
    merge_section(sec, incoming)
    vals = sec.children[0].value
    assert "Rust" in vals and len([v for v in vals if v.lower() == "go"]) == 1


def test_merge_list_appends_entries():
    base = build_section_from_parsed(ExtraSection(
        name="Certs", kind="list",
        entries=[ParsedEntry(fields=[ParsedField(label="Name", value="AWS")])]))
    incoming = build_section_from_parsed(ExtraSection(
        name="Certs", kind="list",
        entries=[ParsedEntry(fields=[ParsedField(label="Name", value="GCP")])]))
    merge_section(base, incoming)
    assert len(base.children[0].children) == 2


def test_merge_markdown_raises():
    a = build_section_from_parsed(ExtraSection(name="About", kind="markdown", markdown="a"))
    b = build_section_from_parsed(ExtraSection(name="About", kind="markdown", markdown="b"))
    with pytest.raises(ValueError):
        merge_section(a, b)
