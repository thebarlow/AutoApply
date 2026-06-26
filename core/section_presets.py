"""Preset section subtrees mirroring the legacy master profile field-for-field.

Migration and (later) the builder gallery both consume these. Item templates
mirror today's stored profile so a migrated profile renders identically.
"""

from __future__ import annotations

from core.profile_tree import FieldNode, GroupNode, ListNode, SectionNode

# Default per-section authoring guidance, distilled from prompts/defaults/resume.md.
# Folded into each per-section generation call by build_section_prompt; the job
# context, field specs, and JSON contract are auto-built around it, so these are
# concise tailoring rules, not full prompts. Keyed by section role.
SECTION_PROMPT_DEFAULTS = {
    "summary": (
        "Lead with the candidate's identity for this specific role — the nature, "
        "scale, and stakes of their actual work — then weave in the role's keywords. "
        "Max 500 characters. Never imply a title, level, or outcome the applicant's "
        "details do not support."
    ),
    "experience": (
        "Max 2 bullets per entry, each at most 120 characters. Stress the skills and "
        "responsibilities named in the job description. Do not reorder, rename, or "
        "invent entries or facts — tailor only the wording."
    ),
    "projects": (
        "Select and order the most relevant projects first; omit irrelevant ones. "
        "Each description is one sentence, at most 120 characters, no bullets."
    ),
    "skills": (
        "Group into at most 6 categories (e.g. Languages, Frameworks, Tools). Include "
        "only categories with 2+ relevant skills; list job-mentioned skills first."
    ),
}

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
        prompt=SECTION_PROMPT_DEFAULTS["summary"],
        children=[
            FieldNode(
                name="Summary", key="hero", kind="markdown", order=0,
                llm_output=True, output_format="paragraph",
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
                name="Summary", key="summary", kind="bullets", order=4,
                llm_output=True, output_format="bullets",
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
                output_format="paragraph",
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
        prompt=SECTION_PROMPT_DEFAULTS["skills"],
        children=[FieldNode(name="Skills", key="skills", kind="taglist")],
    )
