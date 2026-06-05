# tests/core/test_ats_extract.py
from pathlib import Path

from core.ats_gate import extract_text
from core.utils import render_pdf

_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>{{ css }}</style></head>
<body>{{ content_html | safe }}</body></html>
"""


def _render(tmp_path: Path, md: str) -> Path:
    md_path = tmp_path / "in.md"
    md_path.write_text(md, encoding="utf-8")
    tpl = tmp_path / "tpl.html"
    tpl.write_text(_TEMPLATE, encoding="utf-8")
    out = tmp_path / "out.pdf"
    render_pdf(md_path, out, tpl)
    return out


def test_extract_text_returns_body_and_lines(tmp_path: Path):
    pdf = _render(tmp_path, "## Experience\n\nWorked at Acme Corp on Python systems.\n")
    pt = extract_text(pdf)
    assert "Acme Corp" in pt.text
    assert any("Acme Corp" in line for line in pt.lines)


def test_extract_text_empty_for_blank(tmp_path: Path):
    pdf = _render(tmp_path, "\n")
    pt = extract_text(pdf)
    assert pt.text.strip() == ""
