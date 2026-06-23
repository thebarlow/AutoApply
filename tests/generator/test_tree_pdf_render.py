"""Smoke test: tree-v1 résumé renders to PDF with body-only content (no meta)."""

import shutil
from pathlib import Path

import pytest

from core.utils import render_pdf

pytestmark = pytest.mark.skipif(
    shutil.which("pandoc") is None, reason="pandoc not available"
)


def _chromium_ok() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            p.chromium.launch().close()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _chromium_ok(), reason="Chromium not available")
def test_tree_v1_resume_renders_pdf(tmp_path):
    md = "# Jane Doe\n\nj@x.co · 555\n\n## Patents\n\nA patent.\n"
    md_path = tmp_path / "x_resume.md"
    md_path.write_text(md, encoding="utf-8")
    pdf_path = tmp_path / "x_resume.pdf"
    template = Path("generator/resume_template.html")
    render_pdf(md_path, pdf_path, template, max_pages=1, meta={})
    assert pdf_path.exists() and pdf_path.stat().st_size > 0
    from pypdf import PdfReader

    text = "\n".join(
        page.extract_text() or "" for page in PdfReader(str(pdf_path)).pages
    )
    assert "Jane Doe" in text
    assert "patents" in text.lower()
