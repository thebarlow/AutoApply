# tests/core/test_tree_render_e2e.py
"""End-to-end: build a document tree from a legacy profile + custom section, render."""
from __future__ import annotations

from core.document_tree import build_resume_document_tree
from core.profile_tree import FieldNode, GroupNode, ListNode, SectionNode, legacy_to_tree
from core.tree_assembler import assemble_resume_tree_markdown

_PROFILE = {
    "first_name": "Ada", "last_name": "Lovelace", "email": "ada@x.com",
    "hero": "Pioneer.",
    "work_history": [{"company": "Analytical", "title": "Engineer",
                      "start": "1840", "end": "1843", "summary": "Wrote programs."}],
    "education": [{"institution": "Home", "degree": "BS", "field": "Math",
                   "graduated": "1835", "gpa": 4.0}],
    "projects": [], "skills": ["Math", "Logic"],
}


def test_presets_and_custom_section_render_in_tree_order():
    root = legacy_to_tree(_PROFILE)
    custom = SectionNode(name="Awards", role=None, order=99, children=[
        ListNode(name="Awards", item_template=GroupNode(), children=[
            GroupNode(children=[FieldNode(name="Award", key="award",
                                          kind="text", value="First Programmer")]),
        ]),
    ])
    root.children.append(custom)

    # No authored values (simulate generation that changed nothing) — structural snapshot.
    doc = build_resume_document_tree(root, {})
    md = assemble_resume_tree_markdown(doc)

    # Presets present, with their preset formatting.
    assert "### Engineer, Analytical (1840 – 1843)" in md
    assert "**BS in Math**, Home (1835)" in md
    assert "**Skills:** Math, Logic" in md
    # Custom section present and last (tree order).
    assert "## Awards" in md
    assert "**Award:** First Programmer" in md
    assert md.index("## Awards") > md.index("### Engineer")
