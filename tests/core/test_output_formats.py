from __future__ import annotations

from core.output_formats import (
    OutputFormat, get_format, all_formats, BULLETS, PARAGRAPH,
    SKILL_GROUPS,
)


def test_registry_has_expected_formats():
    ids = {f.id for f in all_formats()}
    assert ids == {"bullets", "paragraph", "skill_groups"}


def test_skill_groups_aligns_to_markdown_kind():
    assert SKILL_GROUPS.id == "skill_groups"
    assert SKILL_GROUPS.kind == "markdown"
    assert SKILL_GROUPS.prompt_shape.strip()


def test_bullets_aligns_to_bullets_kind():
    assert BULLETS.id == "bullets"
    assert BULLETS.kind == "bullets"
    assert BULLETS.label == "Bullet list"
    assert BULLETS.prompt_shape.strip()


def test_paragraph_aligns_to_markdown_kind():
    assert PARAGRAPH.id == "paragraph"
    assert PARAGRAPH.kind == "markdown"
    assert PARAGRAPH.label == "Paragraph"


def test_get_format_returns_none_for_unknown():
    assert get_format("nope") is None
    assert get_format("") is None


