"""Golden tests for preset-role formatters (Profile Schema Engine #4A)."""
from __future__ import annotations

from core.profile_tree import FieldNode, GroupNode, RootNode, SectionNode
from core.section_presets import header_section, skills_section, summary_section
from core.tree_assembler import assemble_resume_tree_markdown, _header_section_md


def _header(**vals) -> SectionNode:
    keys = [
        ("first_name", "First Name"), ("last_name", "Last Name"),
        ("email", "Email"), ("phone", "Phone"), ("location", "Location"),
        ("github", "GitHub"), ("linkedin", "LinkedIn"), ("website", "Website"),
    ]
    fields = [
        FieldNode(name=label, key=key, kind="text", order=i, value=vals.get(key, ""))
        for i, (key, label) in enumerate(keys)
    ]
    return SectionNode(name="Header", role="header", order=0,
                       children=[GroupNode(name="Contact", children=fields)])


def test_summary_renders_with_section_name_heading():
    sec = summary_section()
    sec.children[0].value = "Engineer with 5 years experience."
    md = assemble_resume_tree_markdown(RootNode(children=[sec]))
    assert md == "## Summary\n\nEngineer with 5 years experience.\n"


def test_empty_summary_omitted():
    md = assemble_resume_tree_markdown(RootNode(children=[summary_section()]))
    assert md.strip() == ""


def test_skills_renders_inline_joined():
    sec = skills_section()
    sec.children[0].value = ["Python", "FastAPI", "SQL"]
    md = assemble_resume_tree_markdown(RootNode(children=[sec]))
    assert md == "## Skills\n\n**Skills:** Python, FastAPI, SQL\n"


def test_header_name_is_h1_and_contacts_one_line():
    section = _header(
        first_name="Jane", last_name="Doe", email="jane@x.co",
        phone="555-1212", location="Brooklyn, NY",
        github="https://github.com/jane",
    )
    md = _header_section_md(section)
    assert md == (
        "# Jane Doe\n\n"
        "jane@x.co · 555-1212 · Brooklyn, NY · [github.com/jane](https://github.com/jane)"
    )


def test_header_empty_group_returns_blank():
    assert _header_section_md(_header()) == ""


def test_header_skips_blank_fields_preserves_order():
    section = _header(first_name="A", last_name="B", email="a@b.co",
                      website="https://www.site.com/")
    md = _header_section_md(section)
    assert md == "# A B\n\na@b.co · [site.com](https://www.site.com/)"
