from __future__ import annotations

from core.profile_tree import legacy_to_tree, backfill_output_formats, RootNode


def _legacy_tree_with_string_summary():
    """A tree as older profiles stored it: experience summary is a markdown
    string of bullets, no output_format anywhere."""
    root = legacy_to_tree({
        "hero": "I build reliable systems.",
        "work_history": [{"title": "Eng", "company": "Acme", "summary": "- shipped X\n- owned Y"}],
        "projects": [{"name": "P", "description": "A tool."}],
    })
    # Simulate the pre-feature shape: strip output_format and force the legacy kind/value.
    for s in root.children:
        for f in _all_fields(s):
            f.output_format = ""
            if f.key == "summary":
                f.kind = "markdown"
                f.value = "- shipped X\n- owned Y"
    return root


def _all_fields(node):
    out = []
    children = getattr(node, "children", [])
    for c in children:
        if c.type == "field":
            out.append(c)
        else:
            out += _all_fields(c)
    if getattr(node, "type", "") == "list":
        out += _all_fields(node.item_template)
    return out


def test_backfill_splits_experience_string_into_bullets():
    root = _legacy_tree_with_string_summary()
    changed = backfill_output_formats(root)
    assert changed is True
    exp = next(s for s in root.children if s.role == "experience")
    summary = next(f for f in exp.children[0].children[0].children if f.key == "summary")
    assert summary.output_format == "bullets"
    assert summary.kind == "bullets"
    assert summary.value == ["shipped X", "owned Y"]


def test_backfill_sets_paragraph_on_hero_and_description():
    root = _legacy_tree_with_string_summary()
    backfill_output_formats(root)
    hero = next(f for f in _all_fields(next(s for s in root.children if s.role == "summary")) if f.key == "hero")
    desc = next(f for f in _all_fields(next(s for s in root.children if s.role == "projects")) if f.key == "description")
    assert hero.output_format == "paragraph"
    assert desc.output_format == "paragraph"


def test_backfill_is_idempotent():
    root = _legacy_tree_with_string_summary()
    backfill_output_formats(root)
    assert backfill_output_formats(root) is False


def test_backfill_preserves_user_set_format():
    root = _legacy_tree_with_string_summary()
    exp = next(s for s in root.children if s.role == "experience")
    summary = next(f for f in exp.children[0].children[0].children if f.key == "summary")
    summary.output_format = "paragraph"  # user chose paragraph
    summary.kind = "markdown"
    backfill_output_formats(root)
    assert summary.output_format == "paragraph"  # untouched
