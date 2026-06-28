from core.schemas import ParseResponse
from core.parsed_sections import (
    builtin_sections_from_parse, set_section_customize, iter_leaf_fields, _item_name,
)


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
