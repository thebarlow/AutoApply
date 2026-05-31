# tests/core/test_render_pdf.py
from pathlib import Path

import pytest
from pypdf import PdfReader

from core.utils import render_pdf


FIXTURE_MD = """## Experience

**Acme Corp** — Engineer (2020–2024)

- Built things with special chars: & < > % $ — em-dash, café
- Shipped features
"""

MINIMAL_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>{{ css }}</style></head>
<body>{{ content_html | safe }}</body></html>
"""

MINIMAL_CSS = "@page { size: letter; margin: 0.75in; } body { font-family: sans-serif; }"


def _setup(tmp_path: Path) -> tuple[Path, Path, Path]:
    md = tmp_path / "in.md"
    md.write_text(FIXTURE_MD, encoding="utf-8")
    tpl = tmp_path / "tpl.html"
    tpl.write_text(MINIMAL_TEMPLATE, encoding="utf-8")
    css = tmp_path / "tpl.css"
    css.write_text(MINIMAL_CSS, encoding="utf-8")
    return md, tpl, css


def test_render_pdf_produces_valid_pdf(tmp_path: Path):
    md, tpl, _css = _setup(tmp_path)
    out = tmp_path / "out.pdf"
    render_pdf(md, out, tpl)
    assert out.exists() and out.stat().st_size > 0
    reader = PdfReader(str(out))
    assert len(reader.pages) >= 1


def test_render_pdf_handles_special_characters(tmp_path: Path):
    md, tpl, _css = _setup(tmp_path)
    out = tmp_path / "out.pdf"
    render_pdf(md, out, tpl)
    text = PdfReader(str(out)).pages[0].extract_text()
    assert "Acme Corp" in text


def test_render_pdf_max_pages_autoshrinks_borderline(tmp_path: Path):
    # 26 short paragraphs render as 2 pages at full scale but fit on 1 when the
    # print scale is shrunk — auto-shrink should fit it rather than raising.
    border_md = "## Section\n\n" + "".join(
        f"- Bullet line number {i} here.\n" for i in range(26)
    )
    md = tmp_path / "border.md"
    md.write_text(border_md, encoding="utf-8")
    tpl = tmp_path / "tpl.html"
    tpl.write_text(MINIMAL_TEMPLATE, encoding="utf-8")
    css = tmp_path / "tpl.css"
    css.write_text(
        "@page { size: letter; margin: 0.75in; } "
        "body { font-family: sans-serif; font-size: 11pt; line-height: 1.4; }",
        encoding="utf-8",
    )
    out = tmp_path / "out.pdf"
    render_pdf(md, out, tpl, max_pages=1)
    assert len(PdfReader(str(out)).pages) == 1


def test_render_pdf_max_pages_raises_on_overflow(tmp_path: Path):
    big_md = "## Section\n\n" + ("This is a long paragraph. " * 200 + "\n\n") * 30
    md = tmp_path / "big.md"
    md.write_text(big_md, encoding="utf-8")
    tpl = tmp_path / "tpl.html"
    tpl.write_text(MINIMAL_TEMPLATE, encoding="utf-8")
    css = tmp_path / "tpl.css"
    css.write_text(MINIMAL_CSS, encoding="utf-8")
    out = tmp_path / "out.pdf"
    with pytest.raises(RuntimeError, match="exceeds"):
        render_pdf(md, out, tpl, max_pages=1)
