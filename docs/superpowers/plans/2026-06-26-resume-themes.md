# #6B-2 Profile-level Résumé Themes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user pick one of three curated, ATS-safe CSS themes (Classic/Modern/Compact) for their résumé PDFs as a profile-level setting, applied at render time and re-applied on open when the theme changed.

**Architecture:** A pure theme registry (`generator/themes.py`) names each theme and its self-contained CSS file. `render_pdf` gains an optional `css_path` override; `generate_resume_pdf` resolves the profile's `resume_theme` and passes the theme's CSS, stamping the theme used onto the `jobs` row. `serve_resume` re-renders before serving when the stored stamp differs from the profile's current theme. A profile-editor `<select>` writes `resume_theme` through the existing profile-update path.

**Tech Stack:** Python 3 / FastAPI / SQLAlchemy (SQLite dev, Postgres hosted) / Alembic / pandoc + Jinja2 + Playwright Chromium; React (Vite + Vitest/RTL).

## Global Constraints

- **Release:** Merge to LOCAL `main` only. Do NOT push `main` until the entire schema-engine swap (#1–#6) is complete.
- **`classic` is the default and equals today's `resume.css`** — an existing profile with no `resume_theme` must render byte-identically to current `main`.
- **`render_pdf(..., css_path=None)` is unchanged behavior** — covers and all non-résumé callers stay byte-identical.
- **Both résumé render paths must work under every theme** — tree-v1 (`.resume > h1` + the following `<p>`) AND legacy (`.resume-header` icon-grid). A theme that styles only one path is a defect.
- **ATS-safe by construction** — every theme keeps selectable text, single-column flow, standard fonts, no text over background images. No user-authored CSS.
- **A NULL `resume_rendered_theme`** (every pre-migration jobs row) is treated as `classic`.
- Python: type hints, `black`, Google-style docstrings. Prefer stdlib.
- Scope: résumé only. Cover letters, structured knobs, free CSS, WYSIWYG, per-document override, and eager batch re-render are OUT.

**Reference:** spec `docs/superpowers/specs/2026-06-26-resume-themes-design.md`. Pattern precedents: `core/output_formats.py` (registry), `web/routers/output_formats.py` (endpoint), `Job._resolve_resume_max_pages` / `User.resume_max_pages` (profile setting), `alembic/versions/aa04bans01_add_account_banned.py` (add-column migration).

---

### Task 1: Theme registry

**Files:**
- Create: `generator/themes.py`
- Test: `tests/generator/test_themes.py`

**Interfaces:**
- Produces: `Theme(id: str, label: str, css_filename: str)` frozen dataclass; `THEMES: list[Theme]`; `DEFAULT_THEME_ID = "classic"`; `get_theme(theme_id: str) -> Theme | None`; `all_themes() -> list[Theme]`; `resolve_theme(theme_id: str | None) -> Theme` (None/""/unknown → CLASSIC). `CLASSIC.css_filename == "resume.css"`; `MODERN.css_filename == "themes/resume_modern.css"`; `COMPACT.css_filename == "themes/resume_compact.css"`. `css_filename` is relative to the `generator/` directory.

- [ ] **Step 1: Write the failing test**

```python
# tests/generator/test_themes.py
from generator.themes import (
    Theme, THEMES, DEFAULT_THEME_ID, get_theme, all_themes, resolve_theme,
    CLASSIC, MODERN, COMPACT,
)


def test_three_themes_with_ids_and_labels():
    assert [t.id for t in THEMES] == ["classic", "modern", "compact"]
    assert [t.label for t in THEMES] == ["Classic", "Modern", "Compact"]


def test_classic_points_at_existing_resume_css():
    assert CLASSIC.css_filename == "resume.css"
    assert MODERN.css_filename == "themes/resume_modern.css"
    assert COMPACT.css_filename == "themes/resume_compact.css"


def test_default_is_classic():
    assert DEFAULT_THEME_ID == "classic"
    assert get_theme(DEFAULT_THEME_ID) is CLASSIC


def test_get_theme_unknown_returns_none():
    assert get_theme("nope") is None


def test_all_themes_is_ordered_copy():
    assert all_themes() == THEMES


def test_resolve_theme_falls_back_to_classic():
    assert resolve_theme(None) is CLASSIC
    assert resolve_theme("") is CLASSIC
    assert resolve_theme("garbage") is CLASSIC
    assert resolve_theme("modern") is MODERN
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/generator/test_themes.py -q`
Expected: FAIL (ModuleNotFoundError: generator.themes)

- [ ] **Step 3: Write minimal implementation**

```python
# generator/themes.py
"""Curated, ATS-safe résumé theme registry.

A theme names a self-contained résumé stylesheet. ``classic`` maps to the
existing ``generator/resume.css`` (the default; byte-identical to legacy);
``modern`` and ``compact`` live under ``generator/themes/``. ``css_filename``
is relative to the ``generator/`` directory.
"""
from __future__ import annotations

import dataclasses


@dataclasses.dataclass(frozen=True)
class Theme:
    """A selectable résumé theme.

    Attributes:
        id: Stable identifier stored on the profile and the rendered job row.
        label: Human-facing name shown in the picker.
        css_filename: Stylesheet path relative to the ``generator/`` directory.
    """

    id: str
    label: str
    css_filename: str


CLASSIC = Theme(id="classic", label="Classic", css_filename="resume.css")
MODERN = Theme(id="modern", label="Modern", css_filename="themes/resume_modern.css")
COMPACT = Theme(id="compact", label="Compact", css_filename="themes/resume_compact.css")

THEMES: list[Theme] = [CLASSIC, MODERN, COMPACT]
DEFAULT_THEME_ID = "classic"

_BY_ID = {t.id: t for t in THEMES}


def get_theme(theme_id: str) -> Theme | None:
    """Return the theme with ``theme_id``, or ``None`` if unknown."""
    return _BY_ID.get(theme_id)


def all_themes() -> list[Theme]:
    """Return the themes in display order."""
    return list(THEMES)


def resolve_theme(theme_id: str | None) -> Theme:
    """Return the named theme, falling back to ``CLASSIC`` for None/""/unknown."""
    if not theme_id:
        return CLASSIC
    return _BY_ID.get(theme_id, CLASSIC)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/generator/test_themes.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add generator/themes.py tests/generator/test_themes.py
git commit -m "[feat] Add résumé theme registry (classic/modern/compact)"
```

---

### Task 2: `render_pdf` CSS-path override

**Files:**
- Modify: `core/utils.py` (`render_pdf`, around lines 64-108)
- Test: `tests/core/test_render_pdf_css_path.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `render_pdf(md_path, pdf_path, template_path, max_pages=None, meta=None, css_path: Path | None = None)`. When `css_path` is None, behavior is unchanged (CSS derived from the template stem). When given, that file's text is inlined instead.

- [ ] **Step 1: Write the failing test**

Use a fake that captures the rendered HTML by monkeypatching pandoc + Playwright is heavy; instead test the CSS-selection branch directly by asserting the inlined CSS. The simplest seam: patch `sync_playwright` to a no-op and capture the `html` passed to Jinja by patching `Environment`. To avoid that complexity, test the smaller helper behavior via a monkeypatched render that records the CSS string.

```python
# tests/core/test_render_pdf_css_path.py
from pathlib import Path

import core.utils as utils


def _stub_pipeline(monkeypatch, captured):
    """Patch pandoc + Playwright so render_pdf runs without external tools."""
    monkeypatch.setattr(utils.subprocess, "run",
                        lambda *a, **k: type("R", (), {"stdout": "<p>body</p>"})())

    class _FakeEnv:
        def __init__(self, *a, **k):
            self.filters = {}
        def from_string(self, _tpl):
            env = self
            class _T:
                def render(self, **kw):
                    captured["css"] = kw.get("css", "")
                    return "<html></html>"
            return _T()
    monkeypatch.setattr(utils, "Environment", _FakeEnv)

    class _FakeCtx:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def chromium(self): return self
    # sync_playwright() -> ctx manager yielding object with .chromium.launch...
    monkeypatch.setattr(utils, "sync_playwright", lambda: _FakeBrowserCtx())


class _FakeBrowserCtx:
    def __enter__(self): return _FakeP()
    def __exit__(self, *a): return False


class _FakeP:
    @property
    def chromium(self): return self
    def launch(self, *a, **k): return self
    def new_page(self, *a, **k): return self
    def set_content(self, *a, **k): pass
    def pdf(self, *a, **k):
        path = Path(k.get("path"))
        path.write_bytes(b"%PDF-1.4 fake")
    def emulate_media(self, *a, **k): pass
    def close(self, *a, **k): pass


def test_css_path_override_is_inlined(tmp_path, monkeypatch):
    captured = {}
    _stub_pipeline(monkeypatch, captured)
    md = tmp_path / "r.md"; md.write_text("hello", encoding="utf-8")
    css = tmp_path / "custom.css"; css.write_text(".x{color:red}", encoding="utf-8")
    tpl = tmp_path / "resume_template.html"; tpl.write_text("{{ css }}{{ content_html }}", encoding="utf-8")
    utils.render_pdf(md, tmp_path / "out.pdf", tpl, css_path=css)
    assert captured["css"] == ".x{color:red}"


def test_css_path_none_derives_from_template_stem(tmp_path, monkeypatch):
    captured = {}
    _stub_pipeline(monkeypatch, captured)
    md = tmp_path / "r.md"; md.write_text("hello", encoding="utf-8")
    (tmp_path / "resume.css").write_text(".stem{color:blue}", encoding="utf-8")
    tpl = tmp_path / "resume_template.html"; tpl.write_text("{{ css }}{{ content_html }}", encoding="utf-8")
    utils.render_pdf(md, tmp_path / "out.pdf", tpl, css_path=None)
    assert captured["css"] == ".stem{color:blue}"
```

> **Note for implementer:** The Playwright stub above is illustrative — adapt the `_FakeP` method chain to match the EXACT calls `render_pdf` makes (read `core/utils.py` lines 133+ for the real `sync_playwright` usage and mirror it). The behavioral assertions (`captured["css"]`) are what matter; the stub must simply let `render_pdf` reach the Jinja render and write a file without launching Chromium.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/core/test_render_pdf_css_path.py -q`
Expected: FAIL (render_pdf got an unexpected keyword argument 'css_path')

- [ ] **Step 3: Write minimal implementation**

In `core/utils.py`, add the parameter to the signature:

```python
def render_pdf(
    md_path: Path,
    pdf_path: Path,
    template_path: Path,
    max_pages: int | None = None,
    meta: dict | None = None,
    css_path: Path | None = None,
) -> None:
```

Replace the CSS-resolution block (currently lines ~105-108):

```python
    # CSS: explicit override wins; otherwise derive from the template stem
    # (e.g. resume.css for resume_template.html).
    if css_path is None:
        css_stem = template_path.stem.replace("_template", "")
        css_path = template_path.parent / f"{css_stem}.css"
    css = css_path.read_text(encoding="utf-8") if css_path.exists() else ""
```

Add a `css_path:` line to the docstring Args.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/core/test_render_pdf_css_path.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add core/utils.py tests/core/test_render_pdf_css_path.py
git commit -m "[feat] render_pdf: optional css_path override"
```

---

### Task 3: Modern + Compact theme CSS

**Files:**
- Read first: `generator/resume.css` (the full `classic` baseline you are creating variants of)
- Create: `generator/themes/resume_modern.css`
- Create: `generator/themes/resume_compact.css`
- Test: `tests/generator/test_theme_css_render.py`

**Interfaces:**
- Consumes: `render_pdf(css_path=...)` from Task 2; `Theme.css_filename` from Task 1.
- Produces: two standalone résumé stylesheets that style BOTH the tree-v1 selectors (`.resume > h1`, the `<p>` after it, `## Summary`/`h2`, experience headings) AND the legacy `.resume-header` icon-grid, keeping the ATS-safe invariants.

- [ ] **Step 1: Read the baseline**

Read `generator/resume.css` in full. Note every selector it defines — especially the `.resume > h1` tree-v1 contact rules and the legacy `.resume-header` rules (both families MUST be carried into each new theme). Note the page/margin setup and the `_PDF_SCALE_FLOOR` near-one-page expectation from `generator/CONTEXT.md`.

- [ ] **Step 2: Write the failing render test**

```python
# tests/generator/test_theme_css_render.py
"""Smoke test: every theme renders both résumé paths to a non-empty PDF."""
from pathlib import Path

import pytest

import core.utils as utils
from generator.themes import THEMES

GEN = Path(__file__).resolve().parents[2] / "generator"
TEMPLATE = GEN / "resume_template.html"

TREE_V1_MD = "# Jane Doe\n\nNYC · jane@x.com\n\n## Summary\n\nExperienced.\n"
LEGACY_MD = "## Profile\n\nExperienced engineer.\n\n## Experience\n\n### Eng, Acme\n\n- Built.\n"


@pytest.mark.parametrize("theme", THEMES, ids=lambda t: t.id)
@pytest.mark.parametrize("md", [TREE_V1_MD, LEGACY_MD], ids=["tree_v1", "legacy"])
def test_theme_renders_nonempty_pdf(theme, md, tmp_path):
    md_path = tmp_path / "r.md"; md_path.write_text(md, encoding="utf-8")
    pdf_path = tmp_path / "r.pdf"
    css_path = GEN / theme.css_filename
    assert css_path.exists(), f"missing theme CSS {css_path}"
    utils.render_pdf(md_path, pdf_path, TEMPLATE, css_path=css_path)
    assert pdf_path.exists() and pdf_path.stat().st_size > 0
```

> This test invokes real pandoc + Playwright. If the environment lacks them, mark the module with `pytestmark = pytest.mark.skipif(...)` guarded on a `shutil.which("pandoc")` check AND a Playwright-availability check — but the test must run (not skip) in the normal dev/CI environment where both exist. Do not weaken the assertion to make it pass without the CSS files.

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/generator/test_theme_css_render.py -q`
Expected: FAIL (missing theme CSS …/themes/resume_modern.css)

- [ ] **Step 4: Author the two stylesheets**

Create `generator/themes/resume_modern.css` and `generator/themes/resume_compact.css`. Each is a COMPLETE stylesheet (copy `resume.css` as the starting point, then diverge). Requirements for BOTH:

- Carry every selector family from `resume.css`, including the tree-v1 `.resume > h1` contact rules and the legacy `.resume-header` icon-grid rules. Do not delete a selector family.
- Keep the page setup / margins compatible with the one-page shrink behavior.
- ATS-safe: selectable text only, single column, no text over background images, web-standard font families (system sans/serif stacks — no embedded/exotic fonts).

Divergences:
- **Modern:** sans-serif body + headings (system sans stack); lighter/thinner section rules (e.g. hairline border under `h2`); a single restrained accent color applied to heading text or the rule (not large color fills); same structure otherwise.
- **Compact:** tighter page margins, reduced base font-size, reduced section/line spacing and heading margins to pack more content per page; typography family may stay serif like classic — the differentiator is density.

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/generator/test_theme_css_render.py -q`
Expected: PASS (6 passed — 3 themes × 2 paths)

- [ ] **Step 6: Commit**

```bash
git add generator/themes/resume_modern.css generator/themes/resume_compact.css tests/generator/test_theme_css_render.py
git commit -m "[feat] Add Modern and Compact résumé theme stylesheets"
```

---

### Task 4: `User.resume_theme` profile setting

**Files:**
- Modify: `core/user.py` (`_load_from_data` ~line 161; `_to_dict` ~line 192)
- Test: `tests/core/test_user_resume_theme.py`

**Interfaces:**
- Consumes: `DEFAULT_THEME_ID` from `generator.themes`.
- Produces: `User.resume_theme: str` attribute; round-trips through `_to_dict` / `_load_from_data`; missing key → `"classic"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_user_resume_theme.py
import json

from core.user import User


def _user_from_data(d: dict) -> User:
    u = User.__new__(User)
    u.data = json.dumps(d)
    u._load_from_data()  # if the real method name differs, adapt (see Step 3 note)
    return u


def test_missing_key_defaults_to_classic():
    u = _user_from_data({})
    assert u.resume_theme == "classic"


def test_explicit_theme_loads():
    u = _user_from_data({"resume_theme": "modern"})
    assert u.resume_theme == "modern"


def test_round_trips_through_to_dict():
    u = _user_from_data({"resume_theme": "compact"})
    assert u._to_dict()["resume_theme"] == "compact"
```

> **Implementer note:** confirm the actual loader method name in `core/user.py` (the data-loading method that sets `self.resume_max_pages` around line 161). Use the same construction the existing user tests use rather than `__new__` if the file already has a helper/fixture for building a `User` from a data dict — match the existing test style in `tests/core/`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/core/test_user_resume_theme.py -q`
Expected: FAIL (AttributeError: resume_theme)

- [ ] **Step 3: Write minimal implementation**

In `core/user.py`, add the import near the top:

```python
from generator.themes import DEFAULT_THEME_ID
```

In the data loader, immediately after the `self.resume_max_pages = …` line (~161):

```python
        self.resume_theme = raw.get("resume_theme") or DEFAULT_THEME_ID
```

In `_to_dict`, after `d["resume_max_pages"] = self.resume_max_pages` (~192):

```python
        d["resume_theme"] = self.resume_theme
```

> If importing `generator.themes` into `core/user.py` creates a circular import, inline the literal default `"classic"` instead and add a comment referencing `generator.themes.DEFAULT_THEME_ID`. Verify by importing `core.user` standalone.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/core/test_user_resume_theme.py tests/core -q -k "user"`
Expected: PASS (new tests pass; no existing user tests regress)

- [ ] **Step 5: Commit**

```bash
git add core/user.py tests/core/test_user_resume_theme.py
git commit -m "[feat] User.resume_theme profile setting (defaults to classic)"
```

---

### Task 5: `jobs.resume_rendered_theme` column + migration

**Files:**
- Modify: `core/job.py` (Job model artifacts block, ~line 236, add a Column)
- Create: `alembic/versions/aa07themes01_add_jobs_resume_rendered_theme.py`
- Test: `tests/db/test_resume_rendered_theme_migration.py`

**Interfaces:**
- Produces: nullable `Job.resume_rendered_theme` column (String). NULL = "classic".

- [ ] **Step 1: Write the failing test**

```python
# tests/db/test_resume_rendered_theme_migration.py
from core.job import Job


def test_job_has_resume_rendered_theme_column():
    assert "resume_rendered_theme" in Job.__table__.columns


def test_column_is_nullable_string():
    col = Job.__table__.columns["resume_rendered_theme"]
    assert col.nullable is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/db/test_resume_rendered_theme_migration.py -q`
Expected: FAIL (KeyError: resume_rendered_theme)

- [ ] **Step 3: Add the column + migration**

In `core/job.py`, in the Artifacts block after `resume_generated_at` (~line 236):

```python
    resume_rendered_theme = Column(String)  # theme id of the last résumé render; NULL = classic
```

Create the Alembic migration (head is `aa06exttoken01`; confirm with `python -m alembic heads`):

```python
# alembic/versions/aa07themes01_add_jobs_resume_rendered_theme.py
"""add jobs.resume_rendered_theme

Revision ID: aa07themes01
Revises: aa06exttoken01
Create Date: 2026-06-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "aa07themes01"
down_revision: Union[str, Sequence[str], None] = "aa06exttoken01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("resume_rendered_theme", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "resume_rendered_theme")
```

- [ ] **Step 4: Apply the migration and verify**

Run: `python -m alembic upgrade head && python -m pytest tests/db/test_resume_rendered_theme_migration.py -q`
Expected: migration applies; PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add core/job.py alembic/versions/aa07themes01_add_jobs_resume_rendered_theme.py tests/db/test_resume_rendered_theme_migration.py
git commit -m "[feat] Add jobs.resume_rendered_theme column + migration"
```

---

### Task 6: Resolve + apply theme in `generate_resume_pdf`

**Files:**
- Modify: `core/job.py` (add `_resolve_resume_theme`; wire `generate_resume_pdf`, ~lines 1024-1049)
- Test: `tests/core/test_generate_resume_theme.py`

**Interfaces:**
- Consumes: `resolve_theme` from `generator.themes`; `User.resume_theme` (Task 4); `render_pdf(css_path=...)` (Task 2); `Job.resume_rendered_theme` column (Task 5).
- Produces: `Job._resolve_resume_theme(db) -> Theme`. `generate_resume_pdf` passes the resolved theme's CSS path to `render_pdf` and sets `self.resume_rendered_theme = theme.id`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_generate_resume_theme.py
from pathlib import Path

import core.job as job_mod
from core.job import Job
from generator.themes import CLASSIC, MODERN


def test_resolve_default_is_classic(monkeypatch):
    j = Job.__new__(Job); j.profile_id = 1
    monkeypatch.setattr(job_mod.User, "load",
                        staticmethod(lambda db, profile_id=None: type("U", (), {"resume_theme": None})()))
    assert j._resolve_resume_theme(db=None) is CLASSIC


def test_resolve_explicit(monkeypatch):
    j = Job.__new__(Job); j.profile_id = 1
    monkeypatch.setattr(job_mod.User, "load",
                        staticmethod(lambda db, profile_id=None: type("U", (), {"resume_theme": "modern"})()))
    assert j._resolve_resume_theme(db=None) is MODERN


def test_generate_passes_theme_css_and_stamps(monkeypatch, tmp_path):
    # Arrange a Job whose résumé markdown exists.
    j = Job.__new__(Job)
    j.profile_id = 1
    j.job_key = "k1"
    captured = {}

    monkeypatch.setattr(job_mod, "_OUTPUTS_DIR", tmp_path)
    (tmp_path / "k1_resume.md").write_text("# X\n\nbody", encoding="utf-8")
    monkeypatch.setattr(Job, "_resolve_resume_max_pages", lambda self, db: None)
    monkeypatch.setattr(Job, "_render_meta", lambda self, kind, db: {})
    monkeypatch.setattr(Job, "_resolve_resume_theme", lambda self, db: MODERN)

    def _fake_render(md, pdf, tpl, max_pages=None, meta=None, css_path=None):
        captured["css_path"] = css_path
        Path(pdf).write_bytes(b"%PDF fake")
    monkeypatch.setattr(job_mod, "render_pdf", _fake_render)

    class _DB:
        def commit(self): pass
    j.generate_resume_pdf(Path("generator/resume_template.html"), _DB())

    assert captured["css_path"].name == "resume_modern.css"
    assert j.resume_rendered_theme == "modern"
```

> **Implementer note:** match the exact attributes `generate_resume_pdf` touches (it sets `resume_path` and `resume_generated_at` and calls `db.commit()`). Add any attributes the real method reads to the bare `Job.__new__` instance so the test runs. Confirm the `_GENERATOR_DIR`/generator-dir constant name used in `core/job.py` for building the CSS path.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/core/test_generate_resume_theme.py -q`
Expected: FAIL (no attribute `_resolve_resume_theme`)

- [ ] **Step 3: Write minimal implementation**

Add the import near the other `generator` imports in `core/job.py`:

```python
from generator.themes import resolve_theme, Theme
```

Add the resolver next to `_resolve_resume_max_pages`:

```python
    def _resolve_resume_theme(self, db: Session) -> Theme:
        """Résumé theme for this job's owning profile (falls back to classic)."""
        from core.user import User

        user = User.load(db, profile_id=self.profile_id)
        return resolve_theme(user.resume_theme)
```

In `generate_resume_pdf`, resolve the theme, build its CSS path, pass it, and stamp it. The generator directory is the parent of the résumé template; derive the CSS path from it:

```python
        theme = self._resolve_resume_theme(db)
        css_path = template_path.parent / theme.css_filename
        meta = self._render_meta("resume", db)
        render_pdf(md_path, pdf_path, template_path, max_pages=max_pages,
                   meta=meta, css_path=css_path)
        self.resume_path = str(pdf_path)
        self.resume_generated_at = datetime.now(timezone.utc).isoformat()
        self.resume_rendered_theme = theme.id
        db.commit()
```

> `theme.css_filename` is relative to `generator/`, which is exactly `template_path.parent`. For `classic` this yields `generator/resume.css` — identical to the prior derived path, so a classic render stays byte-identical.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/core/test_generate_resume_theme.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add core/job.py tests/core/test_generate_resume_theme.py
git commit -m "[feat] Apply profile résumé theme in generate_resume_pdf + stamp job"
```

---

### Task 7: Re-render on open in `serve_resume`

**Files:**
- Modify: `web/routers/jobs.py` (`serve_resume`, ~lines 405-415)
- Test: `tests/web/test_serve_resume_theme_staleness.py`

**Interfaces:**
- Consumes: `resolve_theme` from `generator.themes`; `User.load`; `Job.resume_rendered_theme`; `Job.generate_resume_pdf`.
- Produces: `serve_resume` re-renders (then serves) when the profile's current theme differs from the job's `resume_rendered_theme` (NULL treated as `"classic"`) AND the résumé markdown exists; otherwise serves the cached file unchanged.

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_serve_resume_theme_staleness.py
from pathlib import Path
from unittest.mock import MagicMock

import web.routers.jobs as jobs_router


def _job(theme, resume_path):
    j = MagicMock()
    j.resume_path = str(resume_path)
    j.resume_rendered_theme = theme
    return j


def test_rerenders_when_theme_differs(monkeypatch, tmp_path):
    pdf = tmp_path / "r.pdf"; pdf.write_bytes(b"%PDF")
    job = _job("classic", pdf)
    monkeypatch.setattr(jobs_router.Job, "get", staticmethod(lambda *a, **k: job))
    monkeypatch.setattr(jobs_router.User, "load",
                        staticmethod(lambda db, profile_id=None: type("U", (), {"resume_theme": "modern"})()))
    monkeypatch.setattr(jobs_router, "_OUTPUTS_DIR", tmp_path) if hasattr(jobs_router, "_OUTPUTS_DIR") else None
    # résumé markdown present so re-render is allowed
    (tmp_path / f"{job.job_key}_resume.md") if False else None
    monkeypatch.setattr(Path, "exists", lambda self: True)
    jobs_router.serve_resume(job_key="k", db=None, profile_id=1)
    job.generate_resume_pdf.assert_called_once()


def test_no_rerender_when_theme_same(monkeypatch, tmp_path):
    pdf = tmp_path / "r.pdf"; pdf.write_bytes(b"%PDF")
    job = _job("modern", pdf)
    monkeypatch.setattr(jobs_router.Job, "get", staticmethod(lambda *a, **k: job))
    monkeypatch.setattr(jobs_router.User, "load",
                        staticmethod(lambda db, profile_id=None: type("U", (), {"resume_theme": "modern"})()))
    monkeypatch.setattr(Path, "exists", lambda self: True)
    jobs_router.serve_resume(job_key="k", db=None, profile_id=1)
    job.generate_resume_pdf.assert_not_called()


def test_null_stamp_classic_profile_no_rerender(monkeypatch, tmp_path):
    pdf = tmp_path / "r.pdf"; pdf.write_bytes(b"%PDF")
    job = _job(None, pdf)
    monkeypatch.setattr(jobs_router.Job, "get", staticmethod(lambda *a, **k: job))
    monkeypatch.setattr(jobs_router.User, "load",
                        staticmethod(lambda db, profile_id=None: type("U", (), {"resume_theme": None})()))
    monkeypatch.setattr(Path, "exists", lambda self: True)
    jobs_router.serve_resume(job_key="k", db=None, profile_id=1)
    job.generate_resume_pdf.assert_not_called()
```

> **Implementer note:** these tests are illustrative of the BEHAVIOR (re-render iff themes differ and markdown exists). Adapt the mocking to the real `serve_resume` body — it returns a `FileResponse`, reads `job.resume_path`, and must check markdown existence before re-rendering. Use the staleness helper from Step 3. If patching `Path.exists` globally is too broad, structure the helper so the markdown-existence check is injectable/mockable, or assert via a real markdown file in `tmp_path` with `_OUTPUTS_DIR` patched. Keep the three behavioral assertions.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/web/test_serve_resume_theme_staleness.py -q`
Expected: FAIL (no re-render path — `generate_resume_pdf` never called)

- [ ] **Step 3: Write minimal implementation**

In `web/routers/jobs.py`, add imports (if not present): `from generator.themes import resolve_theme`, `from core.user import User`, and the résumé template constant `_RESUME_TEMPLATE` already exists (line 46). Update `serve_resume`:

```python
@router.get("/{job_key}/resume")
def serve_resume(job_key: str, db: Session = Depends(get_db),
                 profile_id: int = Depends(current_profile_id)):
    job = Job.get(job_key, db, profile_id=profile_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.resume_path:
        raise HTTPException(status_code=404, detail="Resume not found")

    # Re-render on open if the profile's theme changed since the last render.
    user = User.load(db, profile_id=profile_id)
    current = resolve_theme(user.resume_theme).id
    stamped = job.resume_rendered_theme or "classic"
    md_path = _OUTPUTS_DIR / f"{job_key}_resume.md"
    if current != stamped and md_path.exists():
        job.generate_resume_pdf(_RESUME_TEMPLATE, db)

    path = Path(job.resume_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Resume file missing")
    return FileResponse(path, media_type="application/pdf")
```

> Confirm `_OUTPUTS_DIR` is importable/defined in `web/routers/jobs.py`; if not, import it from `core.job` (where `generate_resume_pdf` uses it) or reuse the same constant the module already references for résumé markdown.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/web/test_serve_resume_theme_staleness.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add web/routers/jobs.py tests/web/test_serve_resume_theme_staleness.py
git commit -m "[feat] serve_resume: re-render on open when profile theme changed"
```

---

### Task 8: `GET /api/themes` endpoint

**Files:**
- Create: `web/routers/themes.py`
- Modify: `web/main.py` (import + `include_router`, mirroring `output_formats_router` at lines 35 / 184)
- Test: `tests/web/test_themes_endpoint.py`

**Interfaces:**
- Consumes: `all_themes()` from `generator.themes`.
- Produces: `GET /api/themes` → `[{"id": ..., "label": ...}, ...]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_themes_endpoint.py
from fastapi.testclient import TestClient

from web.main import app

client = TestClient(app)


def test_themes_endpoint_lists_three():
    r = client.get("/api/themes")
    assert r.status_code == 200
    body = r.json()
    assert [t["id"] for t in body] == ["classic", "modern", "compact"]
    assert [t["label"] for t in body] == ["Classic", "Modern", "Compact"]
```

> If the app requires auth for API routes, mirror exactly how `tests/web/test_output_formats_endpoint.py` constructs its client / auth bypass.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/web/test_themes_endpoint.py -q`
Expected: FAIL (404)

- [ ] **Step 3: Write minimal implementation**

```python
# web/routers/themes.py
from __future__ import annotations

from fastapi import APIRouter

from generator.themes import all_themes

router = APIRouter()


@router.get("/api/themes")
def list_themes() -> list[dict[str, str]]:
    """The résumé theme registry for the profile-editor theme picker."""
    return [{"id": t.id, "label": t.label} for t in all_themes()]
```

In `web/main.py`, mirror the output_formats wiring:

```python
from web.routers import themes as themes_router       # near line 35
...
app.include_router(themes_router.router)              # near line 184
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/web/test_themes_endpoint.py -q`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add web/routers/themes.py web/main.py tests/web/test_themes_endpoint.py
git commit -m "[feat] GET /api/themes endpoint"
```

---

### Task 9: Profile-editor theme picker

**Files:**
- Modify: `react-dashboard/src/api.js` (add `getThemes`, after `getOutputFormats` ~line 75)
- Modify: `react-dashboard/src/components/widgets/ProfileDetail.jsx` (add a `ResumeTheme` control inside the existing "Document" accordion; render it next to `ResumePageLimit` ~line 947)
- Test: `react-dashboard/src/components/widgets/ProfileDetail.theme.test.jsx`

**Interfaces:**
- Consumes: `GET /api/themes` (Task 8); the existing `handleSave(patch)` which does `updateProfile(profileId, { name, data: {...data, ...patch} })`.
- Produces: a `<select>` bound to `d.resume_theme` that calls `onSave({ resume_theme: <id> })`.

- [ ] **Step 1: Write the failing test**

```jsx
// react-dashboard/src/components/widgets/ProfileDetail.theme.test.jsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { ResumeTheme } from './ProfileDetail'

vi.mock('../../api', () => ({
  getThemes: () => Promise.resolve([
    { id: 'classic', label: 'Classic' },
    { id: 'modern', label: 'Modern' },
    { id: 'compact', label: 'Compact' },
  ]),
}))

describe('ResumeTheme', () => {
  it('renders options from getThemes and shows the stored value', async () => {
    render(<ResumeTheme value="modern" onSave={() => {}} />)
    await waitFor(() => expect(screen.getByLabelText(/theme/i)).toBeInTheDocument())
    expect(screen.getByLabelText(/theme/i).value).toBe('modern')
    expect(screen.getByRole('option', { name: 'Compact' })).toBeInTheDocument()
  })

  it('persists the selected theme', async () => {
    const onSave = vi.fn()
    render(<ResumeTheme value="classic" onSave={onSave} />)
    await waitFor(() => screen.getByLabelText(/theme/i))
    fireEvent.change(screen.getByLabelText(/theme/i), { target: { value: 'compact' } })
    expect(onSave).toHaveBeenCalledWith({ resume_theme: 'compact' })
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `react-dashboard/`): `npm run test -- ProfileDetail.theme`
Expected: FAIL (ResumeTheme is not exported)

- [ ] **Step 3: Write minimal implementation**

In `react-dashboard/src/api.js`, after `getOutputFormats`:

```js
export const getThemes = () => _fetch('/api/themes')
```

In `ProfileDetail.jsx`, add the import to the existing `api` import block (`getThemes`) and add the component (place it near `ResumePageLimit`):

```jsx
// Per-profile résumé theme. `value` is the stored theme id (default 'classic').
export function ResumeTheme({ value, onSave }) {
  const [themes, setThemes] = useState([])
  useEffect(() => {
    let alive = true
    const p = getThemes()
    if (p && typeof p.then === 'function') {
      p.then(t => { if (alive) setThemes(Array.isArray(t) ? t : []) }).catch(() => {})
    }
    return () => { alive = false }
  }, [])
  const current = value || 'classic'
  return (
    <div className="flex items-center gap-3">
      <label htmlFor="resume-theme" className="text-xs text-space-dim">Theme</label>
      <select
        id="resume-theme" aria-label="Résumé theme" value={current}
        onChange={(e) => onSave({ resume_theme: e.target.value })}
        className="bg-white text-black border border-space-border rounded px-2 py-1 text-xs"
      >
        {themes.map(t => <option key={t.id} value={t.id}>{t.label}</option>)}
      </select>
    </div>
  )
}
```

Render it inside the same "Document" accordion as `ResumePageLimit`. The cleanest placement: add `<ResumeTheme value={d.resume_theme} onSave={handleSave} />` alongside `<ResumePageLimit … />` at ~line 947. If `ResumePageLimit` owns the `AccordionSection id="document"`, move the theme control inside that section (e.g. render both fields within one "Document" `AccordionSection`) so there is a single Document panel rather than two. Match the existing markup style.

> The `value || 'classic'` guard makes the select controlled even when the profile has no stored theme. The `getThemes` `.then` guard mirrors the `useOutputFormats` non-thenable guard so test mocks returning plain values don't crash.

- [ ] **Step 4: Run test to verify it passes**

Run (from `react-dashboard/`): `npm run test -- ProfileDetail.theme`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add react-dashboard/src/api.js react-dashboard/src/components/widgets/ProfileDetail.jsx react-dashboard/src/components/widgets/ProfileDetail.theme.test.jsx
git commit -m "[feat] Profile-editor résumé theme picker"
```

---

## Final verification (after all tasks)

- [ ] Full backend suite: `python -m pytest -q` — all green, no regressions.
- [ ] Full frontend suite (from `react-dashboard/`): `npm run test` and `npm run build` — all green.
- [ ] Manual smoke (defer to user): pick Modern on a profile, open an existing résumé in the dashboard, confirm the PDF re-renders in the new theme; confirm a classic profile's résumé is unchanged.

## Self-Review notes

- **Spec coverage:** registry (T1), render override (T2), theme CSS for both paths (T3), profile setting (T4), staleness column+migration (T5), resolve+apply+stamp (T6), re-render on open (T7), API (T8), picker UI (T9) — every spec section maps to a task.
- **Back-compat:** classic → `resume.css` via `template_path.parent / "resume.css"` (T6) = byte-identical; `css_path=None` unchanged (T2); NULL stamp = classic (T7).
- **Type consistency:** `resolve_theme`/`get_theme`/`all_themes`/`Theme.css_filename`/`DEFAULT_THEME_ID` used identically across T1/T4/T6/T7/T8; `resume_rendered_theme` column (T5) consumed in T6/T7; `getThemes`/`resume_theme` consistent across T8/T9.
