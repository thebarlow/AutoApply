"""Regression test: bullet string round-trip integrity (feat/output-formats).

A multi-bullet experience summary must survive the save round-trip
(tree_to_legacy → apply_flat_to_tree) without collapsing to a single
element with embedded newlines.
"""

from core.profile_tree import (
    apply_flat_to_tree,
    backfill_output_formats,
    legacy_to_tree,
    tree_to_legacy,
    _section_by_role,
)
from core.tree_assembler import _experience_section_md


_LEGACY = {
    "first_name": "Jane",
    "last_name": "Doe",
    "work_history": [
        {
            "title": "Engineer",
            "company": "Acme",
            "start": "2020",
            "end": "2023",
            "summary": "- shipped X\n- owned Y",
        }
    ],
}


def test_bullet_roundtrip_preserves_two_elements() -> None:
    root = legacy_to_tree(_LEGACY)
    backfill_output_formats(root)

    # Locate the experience summary field and confirm it's already split.
    exp_section = _section_by_role(root, "experience")
    assert exp_section is not None
    list_node = exp_section.children[0]
    summary_field = next(f for f in list_node.children[0].children if f.key == "summary")
    assert summary_field.value == ["shipped X", "owned Y"], (
        f"Before round-trip, expected ['shipped X', 'owned Y'], got {summary_field.value!r}"
    )

    # Simulate save round-trip (the path that was corrupting data).
    flat = tree_to_legacy(root)
    apply_flat_to_tree(root, flat)

    summary_field_after = next(
        f for f in list_node.children[0].children if f.key == "summary"
    )
    assert summary_field_after.value == ["shipped X", "owned Y"], (
        f"After round-trip, expected ['shipped X', 'owned Y'], got {summary_field_after.value!r}"
    )
    # Must be two separate bullets, not one with embedded newline.
    assert len(summary_field_after.value) == 2
    assert "\n" not in summary_field_after.value[0]


def test_bullet_roundtrip_renders_both_bullets() -> None:
    root = legacy_to_tree(_LEGACY)
    backfill_output_formats(root)

    flat = tree_to_legacy(root)
    apply_flat_to_tree(root, flat)

    exp_section = _section_by_role(root, "experience")
    md = _experience_section_md(exp_section)

    assert "- shipped X" in md, f"Missing '- shipped X' in rendered markdown:\n{md}"
    assert "- owned Y" in md, f"Missing '- owned Y' in rendered markdown:\n{md}"
