"""Security hardening of the markdown → HTML → Chromium PDF pipeline (audit H1/M1)."""
from __future__ import annotations

import threading
from pathlib import Path

import pytest

import core.utils as utils
from core.utils import build_render_html, markdown_to_html, render_pdf

GENERATOR = Path(__file__).resolve().parents[2] / "generator"


def _md(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "in.md"
    p.write_text(text, encoding="utf-8")
    return p


# --- pandoc layer ---------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        "a <script>fetch('http://evil/')</script> b",
        '<iframe src="http://internal-host/admin"></iframe>',
        "`<script>x()</script>`{=html}",
        "```{=html}\n<script>y()</script>\n```",
        '<div onclick="z()">hi</div>',
        '<span style="background:url(http://x/)">s</span>',
    ],
)
def test_raw_html_in_markdown_is_not_live(payload: str) -> None:
    html = markdown_to_html(payload)
    assert "<script" not in html
    assert "<iframe" not in html
    assert "<div" not in html
    assert "<span" not in html


def test_legitimate_markdown_still_renders() -> None:
    html = markdown_to_html(
        "## Experience\n\n**Acme** — [site](https://acme.com)\n\n- one\n- two\n\nx & y < z"
    )
    assert '<h2 id="experience">Experience</h2>' in html
    assert "<strong>Acme</strong>" in html
    assert '<a href="https://acme.com">site</a>' in html
    assert "<ul>" in html and "one</" in html
    assert "x &amp; y &lt; z" in html


# --- Jinja layer ----------------------------------------------------------


@pytest.mark.parametrize(
    "template", ["resume_template.html", "master_template.html", "cover_template.html"]
)
def test_meta_fields_are_escaped(tmp_path: Path, template: str) -> None:
    evil = "<img src=x onerror=alert(1)>"
    meta = {
        "name": f"Jane {evil}",
        "firstname": evil,
        "lastname": evil,
        "email": evil,
        "phone": evil,
        "location": evil,
        "linkedin": 'https://l.com/"><script>a()</script>',
        "github": evil,
        "website": evil,
        "company": evil,
        "education": [
            {"degree": evil, "field": evil, "institution": evil, "graduated": evil}
        ],
    }
    html = build_render_html(
        _md(tmp_path, "## Profile\n\nHello.\n\n## Experience\n\nWork."),
        GENERATOR / template,
        meta=meta,
    )
    assert "<img" not in html
    assert "<script" not in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html
    # Trusted HTML still renders as markup: CSS child selectors and body.
    assert "<h2" in html
    assert "&gt;" not in html.split("</style>")[0]


# --- Chromium layer -------------------------------------------------------


class _FakeRequest:
    def __init__(self, url: str) -> None:
        self.url = url


class _FakeRoute:
    def __init__(self, url: str) -> None:
        self.request = _FakeRequest(url)
        self.outcome: str | None = None

    def continue_(self) -> None:
        self.outcome = "continue"

    def abort(self, *_a) -> None:
        self.outcome = "abort"


@pytest.mark.parametrize(
    "url,expected",
    [
        ("http://169.254.169.254/latest/meta-data/", "abort"),
        ("http://internal-host.railway.internal:5432/", "abort"),
        ("https://fonts.googleapis.com/css?family=x", "abort"),
        ("file:///etc/passwd", "abort"),
        ("about:blank", "continue"),
        ("data:image/png;base64,AAAA", "continue"),
    ],
)
def test_route_handler_allowlist(url: str, expected: str) -> None:
    route = _FakeRoute(url)
    utils._route_handler(route)
    assert route.outcome == expected


def test_real_render_blocks_network_image(tmp_path: Path, monkeypatch) -> None:
    pytest.importorskip("playwright.sync_api")
    seen: list[tuple[str, bool]] = []
    real = utils._route_handler

    def _spy(route):
        seen.append((route.request.url, utils._is_allowed_render_url(route.request.url)))
        real(route)

    monkeypatch.setattr(utils, "_route_handler", _spy)
    md = _md(tmp_path, "## Profile\n\n![x](http://169.254.169.254/latest/meta-data/)\n")
    out = tmp_path / "out.pdf"
    render_pdf(md, out, GENERATOR / "master_template.html", meta={"name": "Jane"})
    assert out.stat().st_size > 0
    blocked = [u for u, ok in seen if not ok]
    assert any("169.254.169.254" in u for u in blocked)


def test_real_render_normal_resume(tmp_path: Path) -> None:
    pytest.importorskip("playwright.sync_api")
    from pypdf import PdfReader

    md = _md(
        tmp_path,
        "## Profile\n\nEngineer.\n\n## Experience\n\n**Acme** — Dev\n\n- Built & shipped\n",
    )
    out = tmp_path / "out.pdf"
    render_pdf(
        md,
        out,
        GENERATOR / "resume_template.html",
        max_pages=1,
        meta={"name": "Jane Doe", "email": "j@x.com", "linkedin": "https://linkedin.com/in/j"},
    )
    text = PdfReader(str(out)).pages[0].extract_text()
    assert "Jane Doe" in text
    assert "Built & shipped" in text
    assert "linkedin.com/in/j" in text


# --- concurrency cap ------------------------------------------------------


def test_render_semaphore_is_bounded() -> None:
    assert isinstance(utils._RENDER_SEMAPHORE, type(threading.BoundedSemaphore()))


def test_render_concurrency_env(monkeypatch) -> None:
    monkeypatch.setenv("PDF_RENDER_CONCURRENCY", "5")
    assert utils._render_concurrency() == 5
    monkeypatch.setenv("PDF_RENDER_CONCURRENCY", "junk")
    assert utils._render_concurrency() == 2
    monkeypatch.setenv("PDF_RENDER_CONCURRENCY", "0")
    assert utils._render_concurrency() == 1
