from __future__ import annotations

import re
import subprocess
from datetime import date as _date
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment
from playwright.sync_api import sync_playwright
from pypdf import PdfReader


# Auto-shrink bounds for fitting a PDF within ``max_pages``. The floor caps how
# small text may get (0.8 ≈ 8pt effective for a 10pt base) before we give up and
# raise rather than emit an unreadable document.
_PDF_SCALE_FLOOR = 0.8
_PDF_SCALE_STEP = 0.025


def _strip_url(url: str) -> str:
    return url.replace("https://www.", "").replace("https://", "").replace("http://", "").rstrip("/")


def _split_body_for_education(fragment: str) -> tuple[str, str]:
    """Split a rendered resume body so structured Education can be injected.

    Education must appear as the section immediately after Profile. We strip any
    LLM-generated Education section, then split before the *second* ``<h2>`` —
    whatever it is (Experience, Projects, …) — so Education always lands after
    the opening Profile section, even when no Experience section exists.

    Returns ``(content_pre, content_post)``; ``content_post`` is empty when the
    body has only one section (Education then trails Profile, which is correct).
    """
    fragment_no_edu = re.sub(
        r"<h2[^>]*>\s*Education\s*</h2>.*?(?=<h2|\Z)",
        "",
        fragment,
        flags=re.DOTALL | re.IGNORECASE,
    )
    headers = list(re.finditer(r"<h2[^>]*>", fragment_no_edu, re.IGNORECASE))
    if len(headers) >= 2:
        split = headers[1].start()
        return fragment_no_edu[:split], fragment_no_edu[split:]
    return fragment_no_edu, ""


def _parse_frontmatter(md_path: Path) -> dict[str, Any]:
    """Extract YAML front matter from a markdown file.

    Returns an empty dict if no front matter block is present.
    """
    lines = md_path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            return yaml.safe_load("\n".join(lines[1:i])) or {}
    return {}


def render_pdf(
    md_path: Path,
    pdf_path: Path,
    template_path: Path,
    max_pages: int | None = None,
    meta: dict | None = None,
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
        max_pages: If set, shrink the print scale (down to ``_PDF_SCALE_FLOOR``)
            until the output fits within this page count; raise ``RuntimeError``
            only if it still overflows at the minimum scale. ``None`` disables
            both the limit and auto-shrink.

    Raises:
        subprocess.CalledProcessError: If pandoc exits non-zero.
        RuntimeError: If ``max_pages`` cannot be met even at the minimum scale.
    """
    md_text = md_path.read_text(encoding="utf-8")
    # Ensure bullet lists are preceded by a blank line so pandoc parses them
    # as <ul> elements rather than inline text within a paragraph.
    md_text = re.sub(r"(?<=\S)\n(- )", r"\n\n\1", md_text)

    fragment = subprocess.run(
        ["pandoc", "-t", "html"],
        input=md_text,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout

    # CSS file is named after the doc type (e.g. resume.css for resume_template.html)
    css_stem = template_path.stem.replace("_template", "")
    css_path = template_path.parent / f"{css_stem}.css"
    css = css_path.read_text(encoding="utf-8") if css_path.exists() else ""

    if meta is None:
        meta = _parse_frontmatter(md_path)
    today = _date.today()
    date_str = f"{today.day} {today.strftime('%B')} {today.year}"

    # When frontmatter education is present, inject the structured education
    # block as the second section so the layout is Profile → Education → … .
    content_pre = fragment
    content_post = ""
    if meta.get("education"):
        content_pre, content_post = _split_body_for_education(fragment)

    env = Environment(autoescape=False)
    env.filters["strip_url"] = _strip_url
    html = env.from_string(template_path.read_text(encoding="utf-8")).render(
        css=css,
        content_html=fragment,
        content_pre=content_pre,
        content_post=content_post,
        date=date_str,
        **meta,
    )

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.set_content(html, wait_until="load")
            # Render at full scale first; if the output exceeds max_pages, shrink
            # the print scale step-by-step until it fits. Chromium ignores CSS
            # `zoom` and visual `transform` in its print path, but page.pdf(scale=)
            # genuinely re-lays-out the content, so it reduces the page count.
            scale = 1.0
            while True:
                page.pdf(
                    path=str(pdf_path),
                    format="Letter",
                    print_background=True,
                    scale=round(scale, 3),
                )
                if max_pages is None:
                    break
                page_count = len(PdfReader(str(pdf_path)).pages)
                if page_count <= max_pages:
                    break
                if scale <= _PDF_SCALE_FLOOR + 1e-9:
                    raise RuntimeError(
                        f"Rendered PDF '{pdf_path.name}' still has {page_count} "
                        f"pages at minimum scale {_PDF_SCALE_FLOOR}, exceeds "
                        f"max_pages={max_pages}. Trim the source markdown or regenerate."
                    )
                scale = max(_PDF_SCALE_FLOOR, scale - _PDF_SCALE_STEP)
        finally:
            browser.close()


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
