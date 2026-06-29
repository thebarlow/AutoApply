from __future__ import annotations

from core.utils import markdown_to_html


def test_markdown_to_html_renders_heading_and_paragraph():
    html = markdown_to_html("## Profile\n\nHello world.")
    assert "<h2" in html
    assert "Profile" in html
    assert "Hello world." in html


def test_markdown_to_html_normalizes_tight_bullet_list():
    # A bullet immediately after a line of text must still become a <ul>.
    html = markdown_to_html("Lead in\n- first\n- second")
    assert "<ul>" in html
    # pandoc may render tight (<li>first</li>) or loose (<li><p>first</p></li>)
    # depending on version; check that the content appears inside a list item.
    assert "<li>" in html and "first" in html
