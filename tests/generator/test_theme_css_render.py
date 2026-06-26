"""Smoke test: every theme renders both résumé paths to a non-empty PDF."""
import shutil
from pathlib import Path

import pytest

import core.utils as utils
from generator.themes import THEMES

GEN = Path(__file__).resolve().parents[2] / "generator"
TEMPLATE = GEN / "resume_template.html"

TREE_V1_MD = "# Jane Doe\n\nNYC · jane@x.com\n\n## Summary\n\nExperienced.\n"
LEGACY_MD = "## Profile\n\nExperienced engineer.\n\n## Experience\n\n### Eng, Acme\n\n- Built.\n"

# Guard: skip whole module only when the environment truly lacks the tools.
_pandoc_missing = shutil.which("pandoc") is None
try:
    from playwright.sync_api import sync_playwright as _swp  # noqa: F401
    _playwright_missing = False
except ImportError:
    _playwright_missing = True

pytestmark = pytest.mark.skipif(
    _pandoc_missing or _playwright_missing,
    reason="pandoc or Playwright not available in this environment",
)


@pytest.mark.parametrize("theme", THEMES, ids=lambda t: t.id)
@pytest.mark.parametrize("md", [TREE_V1_MD, LEGACY_MD], ids=["tree_v1", "legacy"])
def test_theme_renders_nonempty_pdf(theme, md, tmp_path):
    md_path = tmp_path / "r.md"
    md_path.write_text(md, encoding="utf-8")
    pdf_path = tmp_path / "r.pdf"
    css_path = GEN / theme.css_filename
    assert css_path.exists(), f"missing theme CSS {css_path}"
    utils.render_pdf(md_path, pdf_path, TEMPLATE, css_path=css_path)
    assert pdf_path.exists() and pdf_path.stat().st_size > 0
