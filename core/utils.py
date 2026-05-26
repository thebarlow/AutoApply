from __future__ import annotations

import subprocess
from pathlib import Path

from jinja2 import Template
from playwright.sync_api import sync_playwright
from pypdf import PdfReader


def render_pdf(
    md_path: Path,
    pdf_path: Path,
    template_path: Path,
    max_pages: int | None = None,
) -> None:
    """Render a Markdown file to PDF via pandoc → Jinja2 HTML → Chromium.

    The template is a Jinja2 HTML file with two slots: ``{{ css }}`` (inlined
    into a ``<style>`` block) and ``{{ content_html }}`` (the pandoc HTML
    fragment). The paired CSS file is loaded from ``<template_stem>.css`` in
    the same directory as the template.

    Args:
        md_path: Path to the source markdown file.
        pdf_path: Destination path for the rendered PDF.
        template_path: Path to the Jinja2 HTML template.
        max_pages: If set, raise ``RuntimeError`` when the output exceeds this
            page count.

    Raises:
        subprocess.CalledProcessError: If pandoc exits non-zero.
        RuntimeError: If ``max_pages`` is exceeded.
    """
    fragment = subprocess.run(
        ["pandoc", str(md_path), "-t", "html"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout

    css_path = template_path.with_suffix(".css")
    css = css_path.read_text(encoding="utf-8") if css_path.exists() else ""

    html = Template(template_path.read_text(encoding="utf-8")).render(
        css=css,
        content_html=fragment,
    )

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.set_content(html, wait_until="load")
            page.pdf(
                path=str(pdf_path),
                format="Letter",
                print_background=True,
            )
        finally:
            browser.close()

    if max_pages is not None:
        page_count = len(PdfReader(str(pdf_path)).pages)
        if page_count > max_pages:
            raise RuntimeError(
                f"Rendered PDF '{pdf_path.name}' has {page_count} pages, "
                f"exceeds max_pages={max_pages}. Trim the source markdown "
                f"or regenerate."
            )


def strip_header_block(md: str) -> str:
    """Remove a name/contact header block from LLM-generated resume markdown.

    Scans past any YAML front matter and any leading non-section lines,
    returning content starting from the first '## ' section header.

    Args:
        md: Raw markdown string, possibly with a header block.

    Returns:
        Markdown string starting from the first section header.
    """
    if not md:
        return md
    lines = md.splitlines()
    i = 0
    if lines and lines[0].strip() == "---":
        i = 1
        while i < len(lines):
            if lines[i].strip() == "---":
                i += 1
                break
            i += 1
    while i < len(lines):
        if lines[i].strip().startswith("## "):
            break
        if i >= 10:
            break
        i += 1
    return "\n".join(lines[i:])
