"""Golden tests for list preset formatters (Profile Schema Engine #4A)."""
from __future__ import annotations

from core.profile_tree import GroupNode, ListNode, RootNode, SectionNode
from core.section_presets import (
    education_template, experience_template, projects_template,
)
from core.tree_assembler import assemble_resume_tree_markdown


def _entry(template_fn, **values) -> GroupNode:
    grp = template_fn()
    for f in grp.children:
        if f.key in values:
            f.value = values[f.key]
    return grp


def _list_section(name: str, role: str, template_fn, entries) -> SectionNode:
    return SectionNode(name=name, role=role, order=0, children=[
        ListNode(name=name, item_template=template_fn(), children=entries),
    ])


def test_experience_entry_heading_and_body():
    e = _entry(experience_template, company="Acme", title="Engineer",
               start="2020", end="2023", summary="Built things.")
    md = assemble_resume_tree_markdown(RootNode(children=[
        _list_section("Experience", "experience", experience_template, [e]),
    ]))
    assert md == (
        "## Experience\n\n"
        "### Engineer, Acme (2020 – 2023)\n\n"
        "Built things.\n"
    )


def test_experience_renamed_section_keeps_user_name():
    e = _entry(experience_template, company="Acme", title="Engineer",
               start="", end="", summary="Did work.")
    md = assemble_resume_tree_markdown(RootNode(children=[
        _list_section("Work History", "experience", experience_template, [e]),
    ]))
    assert md.startswith("## Work History\n\n### Engineer, Acme\n\nDid work.")


def test_education_entry():
    e = _entry(education_template, institution="MIT", degree="BS",
               field="Physics", graduated="2019")
    md = assemble_resume_tree_markdown(RootNode(children=[
        _list_section("Education", "education", education_template, [e]),
    ]))
    assert md == "## Education\n\n**BS in Physics**, MIT (2019)\n"


def test_projects_entry():
    e = _entry(projects_template, name="AutoApply", description="A pipeline.")
    md = assemble_resume_tree_markdown(RootNode(children=[
        _list_section("Projects", "projects", projects_template, [e]),
    ]))
    assert md == "## Projects\n\n**AutoApply**: A pipeline.\n"
