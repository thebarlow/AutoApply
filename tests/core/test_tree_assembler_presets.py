"""Golden tests for preset-role formatters (Profile Schema Engine #4A)."""
from __future__ import annotations

from core.profile_tree import FieldNode, GroupNode, RootNode, SectionNode
from core.section_presets import header_section, skills_section, summary_section
from core.tree_assembler import assemble_resume_tree_markdown


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


def test_header_renders_contact_fields_in_order():
    sec = header_section()
    by_key = {f.key: f for f in sec.children[0].children}
    by_key["email"].value = "a@b.com"
    by_key["phone"].value = "555-0100"
    md = assemble_resume_tree_markdown(RootNode(children=[sec]))
    # email precedes phone (ATS contact order = group field order); empty fields skipped.
    assert md == "## Header\n\n**Email:** a@b.com\n\n**Phone:** 555-0100\n"
