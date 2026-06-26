from __future__ import annotations

from core.profile_tree import legacy_to_tree


def _field(root, role, key):
    section = next(s for s in root.children if s.role == role)
    child = section.children[0]
    if child.type == "list":
        fields = child.children[0].children  # first instance, cloned from template
    elif child.type == "group":
        fields = child.children
    else:
        fields = [child]
    return next(f for f in fields if f.key == key)


def test_experience_summary_defaults_to_bullets():
    root = legacy_to_tree({"work_history": [{"title": "Eng", "company": "Acme", "summary": "x"}]})
    f = _field(root, "experience", "summary")
    assert f.output_format == "bullets"
    assert f.kind == "bullets"


def test_summary_hero_defaults_to_paragraph():
    root = legacy_to_tree({"hero": "I build things."})
    f = _field(root, "summary", "hero")
    assert f.output_format == "paragraph"
    assert f.kind == "markdown"


def test_project_description_defaults_to_paragraph():
    root = legacy_to_tree({"projects": [{"name": "P", "description": "d"}]})
    f = _field(root, "projects", "description")
    assert f.output_format == "paragraph"
    assert f.kind == "markdown"
