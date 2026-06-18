"""Preset section subtrees mirroring the legacy master profile field-for-field.

Migration and (later) the builder gallery both consume these. Item templates
mirror today's stored profile so a migrated profile renders identically.
"""

from __future__ import annotations

from core.profile_tree import FieldNode, GroupNode, ListNode, SectionNode

_HEADER_KEYS = [
    ("first_name", "First Name"),
    ("last_name", "Last Name"),
    ("email", "Email"),
    ("phone", "Phone"),
    ("location", "Location"),
    ("github", "GitHub"),
    ("linkedin", "LinkedIn"),
    ("website", "Website"),
]


def header_section() -> SectionNode:
    """Contact block: a group of text fields keyed by legacy contact field."""
    fields = [
        FieldNode(name=label, key=key, kind="text", order=i)
        for i, (key, label) in enumerate(_HEADER_KEYS)
    ]
    return SectionNode(
        name="Header",
        role="header",
        order=0,
        children=[GroupNode(name="Contact", children=fields)],
    )


def summary_section() -> SectionNode:
    """Profile summary: one markdown field (maps to legacy ``hero``)."""
    return SectionNode(
        name="Summary",
        role="summary",
        order=1,
        children=[
            FieldNode(
                name="Summary", key="hero", kind="markdown", order=0, llm_output=True
            )
        ],
    )


def experience_template() -> GroupNode:
    """One work-history item, mirroring ``WorkHistoryEntry``."""
    return GroupNode(
        name="Experience Item",
        children=[
            FieldNode(name="Company", key="company", kind="text", order=0),
            FieldNode(name="Title", key="title", kind="text", order=1),
            FieldNode(name="Start", key="start", kind="text", order=2),
            FieldNode(name="End", key="end", kind="text", order=3),
            FieldNode(
                name="Summary", key="summary", kind="markdown", order=4, llm_output=True
            ),
        ],
    )


def education_template() -> GroupNode:
    """One education item, mirroring ``EducationEntry``."""
    return GroupNode(
        name="Education Item",
        children=[
            FieldNode(name="Institution", key="institution", kind="text", order=0),
            FieldNode(name="Degree", key="degree", kind="text", order=1),
            FieldNode(name="Field", key="field", kind="text", order=2),
            FieldNode(name="Graduated", key="graduated", kind="text", order=3),
            FieldNode(name="GPA", key="gpa", kind="text", order=4),
        ],
    )


def projects_template() -> GroupNode:
    """One project item, mirroring ``ProjectEntry``."""
    return GroupNode(
        name="Project Item",
        children=[
            FieldNode(name="Name", key="name", kind="text", order=0),
            FieldNode(
                name="Description",
                key="description",
                kind="markdown",
                order=1,
                llm_output=True,
            ),
            FieldNode(name="URL", key="url", kind="text", order=2),
            FieldNode(name="Technologies", key="technologies", kind="taglist", order=3),
        ],
    )


def skills_section() -> SectionNode:
    """Skills: one flat taglist field (mirrors legacy ``skills`` list)."""
    return SectionNode(
        name="Skills",
        role="skills",
        order=5,
        children=[FieldNode(name="Skills", key="skills", kind="taglist")],
    )
