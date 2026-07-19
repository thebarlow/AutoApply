from generator.themes import (
    Theme, THEMES, DEFAULT_THEME_ID, all_themes, resolve_theme,
    CLASSIC, MODERN, COMPACT,
)


def test_three_themes_with_ids_and_labels():
    assert [t.id for t in THEMES] == ["classic", "modern", "compact"]
    assert [t.label for t in THEMES] == ["Classic", "Modern", "Compact"]


def test_classic_points_at_existing_resume_css():
    assert CLASSIC.css_filename == "resume.css"
    assert MODERN.css_filename == "themes/resume_modern.css"
    assert COMPACT.css_filename == "themes/resume_compact.css"


def test_all_themes_is_ordered_copy():
    assert all_themes() == THEMES


def test_resolve_theme_falls_back_to_classic():
    assert resolve_theme(None) is CLASSIC
    assert resolve_theme("") is CLASSIC
    assert resolve_theme("garbage") is CLASSIC
    assert resolve_theme("modern") is MODERN
