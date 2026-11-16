from __future__ import annotations

import logging
import os
import re
import subprocess
import threading
from datetime import date as _date
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment
from markupsafe import Markup
from playwright.sync_api import sync_playwright
from pypdf import PdfReader


# Auto-shrink bounds for fitting a PDF within ``max_pages``. The floor caps how
# small text may get (0.8 ≈ 8pt effective for a 10pt base) before we give up and
# raise rather than emit an unreadable document.
_PDF_SCALE_FLOOR = 0.8
_PDF_SCALE_STEP = 0.025

logger = logging.getLogger(__name__)

# Pandoc input format. Raw HTML is disabled so user/LLM-authored markup
# (``<script>``, ``<iframe>``, …) is emitted as escaped text, never as live
# elements. ``raw_attribute`` (```{=html}``/`` `x`{=html} ``) is a second raw
# passthrough that ``-raw_html`` alone does not close; ``native_divs``/
# ``native_spans`` would otherwise still turn literal ``<div>``/``<span>`` tags
# into elements carrying arbitrary attributes.
_PANDOC_FROM = "markdown-raw_html-raw_attribute-native_divs-native_spans"


def _render_concurrency() -> int:
    try:
        return max(1, int(os.environ.get("PDF_RENDER_CONCURRENCY", "2")))
    except ValueError:
        return 2


# Each render launches a full Chromium; cap how many run at once so concurrent
# requests can't exhaust container memory. Excess callers block (FastAPI runs
# sync endpoints in a threadpool, so this queues rather than rejects).
_RENDER_SEMAPHORE = threading.BoundedSemaphore(_render_concurrency())

# The rendered page is fully self-contained (CSS inlined, SVG icons inline, no
# web fonts), so the only URLs Chromium legitimately touches are the blank
# document set_content writes into and inline data: URIs.
_ALLOWED_URL_PREFIXES = ("about:blank", "data:")


def _is_allowed_render_url(url: str) -> bool:
    """Return True if Chromium may load ``url`` while rendering a PDF."""
    return url.startswith(_ALLOWED_URL_PREFIXES)


def _route_handler(route: Any) -> None:
    """Playwright route handler: abort every request not on the allowlist.

    Blocks SSRF (e.g. ``<img src=http://169.254.169.254/>`` from a markdown
    image or link attribute) and any other network or ``file://`` access.
    """
    url = route.request.url
    if _is_allowed_render_url(url):
        route.continue_()
    else:
        logger.warning("Blocked PDF-render request to %s", url[:200])
        route.abort("blockedbyclient")


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


def markdown_to_html(md_text: str) -> str:
    """Convert a Markdown string to an HTML fragment via pandoc.

    Applies the same tight-bullet-list normalization ``render_pdf`` uses so a
    bullet immediately following a text line is parsed as a ``<ul>``.

    Args:
        md_text: The Markdown source.

    Returns:
        The pandoc-produced HTML fragment.

    Raises:
        subprocess.CalledProcessError: If pandoc exits non-zero.
    """
    md_text = re.sub(r"(?<=\S)\n(- )", r"\n\n\1", md_text)
    return subprocess.run(
        ["pandoc", "-f", _PANDOC_FROM, "-t", "html"],
        input=md_text,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout


def build_render_html(
    md_path: Path,
    template_path: Path,
    meta: dict | None = None,
    css_path: Path | None = None,
) -> str:
    """Build the full HTML document ``render_pdf`` hands to Chromium.

    Every template variable is autoescaped; only the pandoc body fragment (made
    safe by ``_PANDOC_FROM``) and the repo-owned CSS are marked ``Markup``.

    Args:
        md_path: Path to the source markdown file.
        template_path: Path to the Jinja2 HTML template.
        meta: Template variables (contact fields, education, …). When ``None``,
            parsed from the markdown's YAML frontmatter.
        css_path: Optional explicit CSS file to inline. When ``None``, the CSS
            file is derived from the template stem (e.g. ``resume.css`` for
            ``resume_template.html``).

    Returns:
        The rendered HTML document.
    """
    md_text = md_path.read_text(encoding="utf-8")
    fragment = markdown_to_html(md_text)

    # CSS: explicit override wins; otherwise derive from the template stem
    # (e.g. resume.css for resume_template.html).
    if css_path is None:
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

    env = Environment(autoescape=True)
    env.filters["strip_url"] = _strip_url
    return env.from_string(template_path.read_text(encoding="utf-8")).render(
        **meta,
        # Trusted HTML: CSS ships with the repo (themes are a fixed registry) and
        # the body fragment comes from pandoc with raw HTML disabled.
        css=Markup(css),
        content_html=Markup(fragment),
        content_pre=Markup(content_pre),
        content_post=Markup(content_post),
        date=date_str,
    )


def render_pdf(
    md_path: Path,
    pdf_path: Path,
    template_path: Path,
    max_pages: int | None = None,
    meta: dict | None = None,
    css_path: Path | None = None,
) -> None:
    """Render a Markdown file to PDF via pandoc → Jinja2 HTML → Chromium.

    The template is a Jinja2 HTML file with two slots: ``{{ css }}`` (inlined
    into a ``<style>`` block) and ``{{ content_html }}`` (the pandoc HTML
    fragment). By default the paired CSS file is derived from the template stem
    (e.g. ``resume.css`` for ``resume_template.html``); an explicit ``css_path``
    argument overrides this stem-derived default.

    Chromium renders offline with JavaScript disabled: every request except
    ``about:blank``/``data:`` is aborted. Concurrent renders are capped by
    ``PDF_RENDER_CONCURRENCY`` (default 2).

    Args:
        md_path: Path to the source markdown file.
        pdf_path: Destination path for the rendered PDF.
        template_path: Path to the Jinja2 HTML template.
        max_pages: If set, shrink the print scale (down to ``_PDF_SCALE_FLOOR``)
            until the output fits within this page count; raise ``RuntimeError``
            only if it still overflows at the minimum scale. ``None`` disables
            both the limit and auto-shrink.
        meta: Template variables; parsed from frontmatter when ``None``.
        css_path: Optional explicit CSS file to inline. When ``None``, the CSS
            file is derived from the template stem (e.g. ``resume.css`` for
            ``resume_template.html``).

    Raises:
        subprocess.CalledProcessError: If pandoc exits non-zero.
        RuntimeError: If ``max_pages`` cannot be met even at the minimum scale.
    """
    html = build_render_html(md_path, template_path, meta=meta, css_path=css_path)

    with _RENDER_SEMAPHORE, sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            context = browser.new_context(java_script_enabled=False)
            context.route("**/*", _route_handler)
            page = context.new_page()
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
