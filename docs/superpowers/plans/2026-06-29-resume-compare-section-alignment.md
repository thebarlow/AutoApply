# Resume Compare — Section Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the admin Resume Compare harness's free-flowing Markdown columns with a section-aligned grid where each cell renders in PDF styling (`resume.css`) inside an isolated iframe.

**Architecture:** Backend converts each model's assembled Markdown to HTML via pandoc (reusing the existing pandoc step), splits the HTML at `<h2>` boundaries into `{heading, html}` sections, and returns those plus the `resume.css` contents. The React component aligns sections row-by-row (union of headings) and renders each cell in an iframe carrying `resume.css`, equalizing paired row heights so headings line up across models.

**Tech Stack:** Python / FastAPI / pytest (backend); React / Vitest / Testing Library (frontend); pandoc (already a dependency).

## Global Constraints

- Python: type hints, `black` formatting, Google-style docstrings (project CLAUDE.md).
- No DB, schema, prompt, or generator-template changes.
- Existing per-model fields `markdown`, `score`, `issues`, `error` MUST remain for back-compat; new fields are additive.
- Commit format: `[type] Imperative subject` (types: feat, fix, refactor, docs, test, chore). No Claude attribution.
- Backend pandoc invocation pattern (copy verbatim where needed):
  ```python
  subprocess.run(
      ["pandoc", "-t", "html"],
      input=md_text, check=True, capture_output=True, text=True, encoding="utf-8",
  ).stdout
  ```
- `resume.css` path: `generator/resume.css` (relative to repo root). In `core/utils.py` the generator dir is reachable; in `web/routers/dev.py` use a path anchored to the repo (see Task 3).

---

### Task 1: `markdown_to_html` helper in `core/utils.py`

Factor the pandoc Markdown→HTML step out of `render_pdf` into a reusable function so the compare harness can use it without the PDF/Jinja/Chromium path.

**Files:**
- Modify: `core/utils.py` (pandoc block at `core/utils.py:96-108`)
- Test: `tests/test_utils_markdown_to_html.py` (create)

**Interfaces:**
- Produces: `markdown_to_html(md_text: str) -> str` — returns the pandoc HTML fragment. Applies the same bullet-list pre-normalization (`re.sub(r"(?<=\S)\n(- )", r"\n\n\1", md_text)`) `render_pdf` uses.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_utils_markdown_to_html.py
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
    assert "<li>first</li>" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_utils_markdown_to_html.py -v`
Expected: FAIL — `ImportError: cannot import name 'markdown_to_html'`.

- [ ] **Step 3: Add the helper and call it from `render_pdf`**

Add this function above `render_pdf` in `core/utils.py` (it needs `re` and `subprocess`, already imported at the top of the file):

```python
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
        ["pandoc", "-t", "html"],
        input=md_text,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout
```

Then replace the inline pandoc block in `render_pdf` (`core/utils.py:96-108`) so it reuses the helper:

```python
    md_text = md_path.read_text(encoding="utf-8")
    fragment = markdown_to_html(md_text)
```

(Delete the now-redundant `re.sub(...)` line and the inline `subprocess.run(...)` assignment that previously produced `fragment`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_utils_markdown_to_html.py -v`
Expected: PASS (both tests). Requires `pandoc` on PATH.

- [ ] **Step 5: Run the render_pdf regression tests**

Run: `python -m pytest tests/ -k render_pdf -q`
Expected: PASS (no regressions from the refactor). If no such tests exist, this step is a no-op confirmation.

- [ ] **Step 6: Commit**

```bash
git add core/utils.py tests/test_utils_markdown_to_html.py
git commit -m "[refactor] Extract markdown_to_html helper from render_pdf"
```

---

### Task 2: `_split_sections_html` in `web/routers/dev.py`

Split a pandoc HTML fragment into top-level sections at `<h2>` boundaries.

**Files:**
- Modify: `web/routers/dev.py`
- Test: `tests/web/test_resume_compare.py`

**Interfaces:**
- Produces: `_split_sections_html(html: str) -> list[dict]` where each dict is
  `{"heading": str, "html": str}`.
  - Content before the first `<h2>` → one leading section `{"heading": "Header", "html": <that content>}` (only if that content is non-empty after stripping).
  - Each `<h2>...` starts a new section; `heading` is the `<h2>`'s text content stripped of tags/whitespace; `html` is the `<h2>` plus everything up to (excluding) the next `<h2>`.
  - No `<h2>` present → single `{"heading": "Header", "html": html}` (when non-empty).
  - Empty/whitespace input → `[]`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/web/test_resume_compare.py`:

```python
def test_split_sections_html_header_then_sections():
    html = (
        '<h1>Jane Doe</h1><p>jane@x.com</p>'
        '<h2 id="profile">Profile</h2><p>Summary.</p>'
        '<h2 id="skills">Skills</h2><ul><li>Python</li></ul>'
    )
    out = devmod._split_sections_html(html)
    assert [s["heading"] for s in out] == ["Header", "Profile", "Skills"]
    assert "Jane Doe" in out[0]["html"]
    assert out[1]["html"].startswith("<h2")
    assert "Summary." in out[1]["html"]
    assert "Python" in out[2]["html"]
    # Profile section must not bleed into Skills content.
    assert "Python" not in out[1]["html"]


def test_split_sections_html_no_h2_is_single_header():
    out = devmod._split_sections_html("<p>just a blurb</p>")
    assert out == [{"heading": "Header", "html": "<p>just a blurb</p>"}]


def test_split_sections_html_empty():
    assert devmod._split_sections_html("   ") == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/web/test_resume_compare.py -k split_sections -v`
Expected: FAIL — `AttributeError: module 'web.routers.dev' has no attribute '_split_sections_html'`.

- [ ] **Step 3: Implement the helper**

Add near the top of `web/routers/dev.py` (after the imports). Add `import re` to the import block:

```python
_H2_RE = re.compile(r"<h2\b", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


def _split_sections_html(html: str) -> list[dict]:
    """Split a pandoc HTML fragment into top-level sections at ``<h2>`` boundaries.

    Content preceding the first ``<h2>`` (e.g. a tree-v1 name ``<h1>`` and contact
    ``<p>``) is returned as a leading ``"Header"`` section.

    Args:
        html: The HTML fragment to split.

    Returns:
        Ordered list of ``{"heading": str, "html": str}`` dicts. Empty input
        yields ``[]``.
    """
    if not html or not html.strip():
        return []

    # Indices where each <h2 begins; everything before the first is the header.
    starts = [m.start() for m in _H2_RE.finditer(html)]
    sections: list[dict] = []

    if not starts:
        return [{"heading": "Header", "html": html.strip()}]

    header = html[: starts[0]].strip()
    if header:
        sections.append({"heading": "Header", "html": header})

    bounds = starts + [len(html)]
    for i in range(len(starts)):
        chunk = html[bounds[i] : bounds[i + 1]].strip()
        # Heading text = inner text of the opening <h2>...</h2>.
        end = chunk.lower().find("</h2>")
        open_tag_end = chunk.find(">")
        heading = (
            _TAG_RE.sub("", chunk[open_tag_end + 1 : end]).strip()
            if end != -1 and open_tag_end != -1
            else "Section"
        )
        sections.append({"heading": heading, "html": chunk})

    return sections
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/web/test_resume_compare.py -k split_sections -v`
Expected: PASS (all three).

- [ ] **Step 5: Commit**

```bash
git add web/routers/dev.py tests/web/test_resume_compare.py
git commit -m "[feat] Split compare HTML into aligned sections by h2"
```

---

### Task 3: Wire sections + css into the compare response

Make `_one_model` attach `sections` and `run_comparison` attach top-level `css`.

**Files:**
- Modify: `web/routers/dev.py` (`_one_model` at `web/routers/dev.py:59-67`, `run_comparison` at `web/routers/dev.py:70-75`)
- Test: `tests/web/test_resume_compare.py`

**Interfaces:**
- Consumes: `markdown_to_html` (Task 1), `_split_sections_html` (Task 2).
- Produces:
  - `_one_model(...)` result dict additionally contains `sections: list[dict]` on success (unchanged `{"error": ...}` on failure — no `sections`).
  - `run_comparison(...)` return dict additionally contains `css: str` at top level (contents of `generator/resume.css`, or `""` if unreadable).

- [ ] **Step 1: Write the failing tests**

Add to `tests/web/test_resume_compare.py`:

```python
def test_run_comparison_includes_sections_and_css(monkeypatch):
    monkeypatch.setattr(
        devmod, "_model1_markdown",
        lambda job, user, client, model, db: "## Profile\n\nONE body",
    )
    monkeypatch.setattr(
        devmod, "_model2_markdown",
        lambda job, user, client, model, db: "## Profile\n\nTWO body",
    )
    out = devmod.run_comparison(
        _Job(), user=object(), client=object(), model="m",
        eval_prompt="EVAL {current_document}", db=None,
    )
    assert isinstance(out["css"], str)
    assert out["css"]  # resume.css is non-empty
    headings = [s["heading"] for s in out["model1"]["sections"]]
    assert "Profile" in headings


def test_run_comparison_errored_model_still_has_css(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("nope")
    monkeypatch.setattr(devmod, "_model1_markdown", boom)
    monkeypatch.setattr(
        devmod, "_model2_markdown",
        lambda *a, **k: "## Profile\n\nok",
    )
    out = devmod.run_comparison(
        _Job(), user=object(), client=object(), model="m",
        eval_prompt="EVAL {current_document}", db=None,
    )
    assert "error" in out["model1"]
    assert "sections" not in out["model1"]
    assert isinstance(out["css"], str)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/web/test_resume_compare.py -k "sections_and_css or errored_model_still_has_css" -v`
Expected: FAIL — `KeyError: 'css'` / missing `sections`.

- [ ] **Step 3: Implement**

Add a module-level CSS path constant near the top of `web/routers/dev.py` (after imports). Anchor it to the repo root via the existing package layout — `core/utils.py` already resolves generator files relative to the repo, but to keep dev.py self-contained derive it from this file's location:

```python
from pathlib import Path

_RESUME_CSS = Path(__file__).resolve().parents[2] / "generator" / "resume.css"
```

(`parents[2]` of `web/routers/dev.py` is the repo root. Verify in Step 4 that the css loads non-empty.)

Update `_one_model` to attach sections on success (replace `web/routers/dev.py:59-67`):

```python
def _one_model(fn, job, user, client, model, eval_prompt, db) -> dict:
    """Run one model's markdown fn + eval; capture failures per-model."""
    try:
        md = fn(job, user, client, model, db)
    except Exception as exc:  # noqa: BLE001 — surface to the page, never 500 the pair
        return {"error": str(exc)}
    result = {"markdown": md, "sections": _split_sections_html(markdown_to_html(md))}
    result.update(job.evaluate_resume_body(md, eval_prompt, user, client, model))
    return result
```

Update `run_comparison` to attach css (replace `web/routers/dev.py:70-75`):

```python
def run_comparison(job, user, client, model, eval_prompt, db) -> dict:
    """Run both models independently and return both results plus the résumé CSS."""
    css = _RESUME_CSS.read_text(encoding="utf-8") if _RESUME_CSS.exists() else ""
    return {
        "css": css,
        "model1": _one_model(_model1_markdown, job, user, client, model, eval_prompt, db),
        "model2": _one_model(_model2_markdown, job, user, client, model, eval_prompt, db),
    }
```

Add the imports at the top of `web/routers/dev.py`:

```python
from core.utils import markdown_to_html
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/web/test_resume_compare.py -v`
Expected: PASS (all tests, including the pre-existing ones). The pre-existing `test_run_comparison_returns_both_models` still passes because `markdown`/`score` are unchanged.

- [ ] **Step 5: Commit**

```bash
git add web/routers/dev.py tests/web/test_resume_compare.py
git commit -m "[feat] Return per-model sections and resume CSS from compare harness"
```

---

### Task 4: Section-aligned grid in `ResumeCompare.jsx`

Render the aligned two-column section grid with PDF-styled iframe cells and equalized row heights.

**Files:**
- Modify: `react-dashboard/src/components/admin/ResumeCompare.jsx`
- Test: `react-dashboard/src/components/admin/ResumeCompare.test.jsx`

**Interfaces:**
- Consumes: `resumeCompare(jobKey)` → `{ css, model1, model2 }` where each model is
  `{ markdown, score, issues, sections: [{heading, html}] }` or `{ error }` (Task 3).
- Produces: UI only (no exported functions).

**Behavior contract (implement exactly):**
- Build rows from the **union** of headings across both models, matched case-insensitively (trim + lowercase as the match key). Row order = Model 1's heading order, then any Model-2-only headings appended in Model 2 order.
- Each row renders the heading once (small label) plus two cells. A cell with a section renders an iframe; a cell with no section for that model renders a muted `— not present —`.
- Each iframe's `srcDoc` is `<style>${css}</style><div class="resume">${html}</div>`.
- After both iframes in a row load, set both their heights to the max of the two content heights (`contentDocument.documentElement.scrollHeight`).
- A model with `error` shows its error message in that column's header area; the grid still renders the healthy model's cells (the errored column shows `— error —` placeholders). If BOTH error, show only the error banner(s), no grid.
- Sticky header row shows both model titles + `score N.NN` (kept from current).

- [ ] **Step 1: Update the failing test**

Replace `react-dashboard/src/components/admin/ResumeCompare.test.jsx` with:

```jsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import ResumeCompare from './ResumeCompare'
import * as api from '../../api'

const CSS = '.resume { color: #111; }'

describe('ResumeCompare', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('aligns sections in rows with scores in the header', async () => {
    vi.spyOn(api, 'resumeCompare').mockResolvedValue({
      css: CSS,
      model1: {
        markdown: 'x', score: 0.7, issues: [],
        sections: [
          { heading: 'Profile', html: '<h2>Profile</h2><p>one profile</p>' },
          { heading: 'Skills', html: '<h2>Skills</h2><p>one skills</p>' },
        ],
      },
      model2: {
        markdown: 'y', score: 0.9, issues: [],
        sections: [
          { heading: 'Profile', html: '<h2>Profile</h2><p>two profile</p>' },
        ],
      },
    })
    render(<ResumeCompare />)
    fireEvent.change(screen.getByLabelText('Job key'), { target: { value: 'job-1' } })
    fireEvent.click(screen.getByText('Compare'))
    await waitFor(() => expect(api.resumeCompare).toHaveBeenCalledWith('job-1'))

    // Heading labels (rendered as row labels, not inside iframes) — union, model1 order first.
    expect(await screen.findByText('Profile')).toBeInTheDocument()
    expect(screen.getByText('Skills')).toBeInTheDocument()
    // Scores in header row.
    expect(screen.getByText(/0\.7/)).toBeInTheDocument()
    expect(screen.getByText(/0\.9/)).toBeInTheDocument()
    // Model 2 lacks Skills → a "not present" placeholder appears.
    expect(screen.getByText(/not present/i)).toBeInTheDocument()
    // Cells are iframes carrying the section html via srcDoc.
    const frames = document.querySelectorAll('iframe')
    expect(frames.length).toBe(3) // 2 model1 + 1 model2
    expect(frames[0].getAttribute('srcdoc')).toContain('one profile')
    expect(frames[0].getAttribute('srcdoc')).toContain(CSS)
  })

  it('shows a model error without crashing the other column', async () => {
    vi.spyOn(api, 'resumeCompare').mockResolvedValue({
      css: CSS,
      model1: { error: 'boom' },
      model2: {
        markdown: 'y', score: 0.9, issues: [],
        sections: [{ heading: 'Profile', html: '<h2>Profile</h2><p>ok</p>' }],
      },
    })
    render(<ResumeCompare />)
    fireEvent.change(screen.getByLabelText('Job key'), { target: { value: 'j' } })
    fireEvent.click(screen.getByText('Compare'))
    expect(await screen.findByText(/boom/)).toBeInTheDocument()
    // Healthy model still renders its section iframe.
    const frames = document.querySelectorAll('iframe')
    expect(frames.length).toBe(1)
    expect(frames[0].getAttribute('srcdoc')).toContain('ok')
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd react-dashboard && npm test -- ResumeCompare`
Expected: FAIL — current component renders Markdown columns, no iframes / heading labels.

- [ ] **Step 3: Implement the component**

Replace `react-dashboard/src/components/admin/ResumeCompare.jsx` with:

```jsx
import { useState, useRef, useCallback } from 'react'
import { resumeCompare } from '../../api'

function buildRows(m1, m2) {
  const s1 = m1?.sections || []
  const s2 = m2?.sections || []
  const key = (h) => h.trim().toLowerCase()
  const map2 = new Map(s2.map((s) => [key(s.heading), s]))
  const rows = []
  const seen = new Set()
  for (const s of s1) {
    const k = key(s.heading)
    seen.add(k)
    rows.push({ heading: s.heading, m1: s, m2: map2.get(k) || null })
  }
  for (const s of s2) {
    const k = key(s.heading)
    if (seen.has(k)) continue
    rows.push({ heading: s.heading, m1: null, m2: s })
  }
  return rows
}

function srcDoc(css, html) {
  return `<style>${css}</style><div class="resume">${html}</div>`
}

function Cell({ css, section, errored, registerFrame }) {
  if (errored) return <div className="text-red-400/70 text-xs italic p-2">— error —</div>
  if (!section) return <div className="text-space-dim text-xs italic p-2">— not present —</div>
  return (
    <iframe
      title="section"
      srcDoc={srcDoc(css, section.html)}
      ref={registerFrame}
      className="w-full bg-white rounded border border-space-border"
      style={{ height: 80, border: 'none' }}
    />
  )
}

function HeaderCell({ title, model }) {
  return (
    <div className="flex items-center justify-between px-1 pb-2 border-b border-space-border">
      <h3 className="font-semibold text-sm">{title}</h3>
      {model?.error == null && model?.score != null && (
        <span className="text-xs text-space-dim">score {Number(model.score).toFixed(2)}</span>
      )}
      {model?.error != null && <span className="text-red-400 text-xs">Error: {model.error}</span>}
    </div>
  )
}

export default function ResumeCompare() {
  const [jobKey, setJobKey] = useState('')
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  // rowKey -> { left, right } iframe element refs, for height equalization.
  const frames = useRef({})

  const run = async () => {
    setBusy(true); setErr(''); setResult(null); frames.current = {}
    try {
      setResult(await resumeCompare(jobKey.trim()))
    } catch (e) {
      setErr(String(e.message || e))
    } finally {
      setBusy(false)
    }
  }

  // Equalize the two iframes in a row to the taller content height once both loaded.
  const equalize = useCallback((rowKey) => {
    const pair = frames.current[rowKey]
    if (!pair) return
    const heights = []
    for (const f of [pair.left, pair.right]) {
      if (!f) continue
      try {
        heights.push(f.contentDocument.documentElement.scrollHeight)
      } catch { /* not ready */ }
    }
    if (!heights.length) return
    const h = Math.max(...heights)
    for (const f of [pair.left, pair.right]) if (f) f.style.height = `${h}px`
  }, [])

  const register = (rowKey, side) => (el) => {
    if (!el) return
    frames.current[rowKey] = frames.current[rowKey] || {}
    frames.current[rowKey][side] = el
    el.addEventListener('load', () => equalize(rowKey), { once: true })
  }

  const m1 = result?.model1
  const m2 = result?.model2
  const bothErrored = m1?.error != null && m2?.error != null
  const rows = result && !bothErrored ? buildRows(m1, m2) : []

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-end gap-2">
        <label className="flex flex-col text-sm gap-1">
          <span className="text-space-dim">Job key</span>
          <input
            aria-label="Job key" value={jobKey}
            className="bg-white/5 border border-space-border rounded px-2 py-1 text-sm"
            onChange={(e) => setJobKey(e.target.value)}
          />
        </label>
        <button
          type="button" disabled={busy || !jobKey.trim()}
          className="px-3 py-1.5 rounded-lg border border-space-border bg-[#1a1a2e] hover:bg-[#23233a] disabled:opacity-50"
          onClick={run}
        >{busy ? 'Comparing…' : 'Compare'}</button>
      </div>
      {err && <p className="text-red-400 text-sm">{err}</p>}

      {result && (
        <div className="flex flex-col gap-3">
          {/* Sticky header row */}
          <div className="grid grid-cols-[7rem_1fr_1fr] gap-3 sticky top-0 bg-space-bg z-10 pt-1">
            <div />
            <HeaderCell title="Model 1 (single-call)" model={m1} />
            <HeaderCell title="Model 2 (per-section)" model={m2} />
          </div>

          {bothErrored && (
            <p className="text-red-400 text-sm">Both models failed; nothing to compare.</p>
          )}

          {rows.map((row, i) => {
            const rowKey = `${i}:${row.heading}`
            return (
              <div key={rowKey} className="grid grid-cols-[7rem_1fr_1fr] gap-3 items-start">
                <div className="text-xs font-semibold text-space-dim uppercase tracking-wide pt-2">
                  {row.heading}
                </div>
                <Cell css={result.css} section={row.m1} errored={m1?.error != null}
                  registerFrame={register(rowKey, 'left')} />
                <Cell css={result.css} section={row.m2} errored={m2?.error != null}
                  registerFrame={register(rowKey, 'right')} />
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd react-dashboard && npm test -- ResumeCompare`
Expected: PASS (both tests). Note: jsdom does not fire iframe `load` or compute real `scrollHeight`, so the equalization is exercised but heights stay at the default — the tests assert structure/`srcDoc`, not pixel heights.

- [ ] **Step 5: Commit**

```bash
git add react-dashboard/src/components/admin/ResumeCompare.jsx react-dashboard/src/components/admin/ResumeCompare.test.jsx
git commit -m "[feat] Section-aligned PDF-styled Resume Compare grid"
```

---

### Task 5: Manual verification + docs

**Files:**
- Modify: `react-dashboard/CONTEXT.md` and/or `web/CONTEXT.md` (whichever documents the compare harness) — note the new section-aligned, iframe-based rendering and the `sections`/`css` response fields.

- [ ] **Step 1: Run the full affected test suites**

Run: `python -m pytest tests/web/test_resume_compare.py tests/test_utils_markdown_to_html.py -q`
Run: `cd react-dashboard && npm test -- ResumeCompare`
Expected: all PASS.

- [ ] **Step 2: Manual smoke (admin)**

Start the app (`start.bat dev`), open the Admin panel → Resume Compare, enter an **extracted** job key, click Compare. Confirm:
- Sections appear as aligned rows; the same heading lines up across both columns.
- Each cell looks like the PDF (serif ALL-CAPS headers, Helvetica body, white background).
- A heading missing in one model shows `— not present —`.
- Scores show in the header row.

- [ ] **Step 3: Update CONTEXT docs**

Document in the relevant `CONTEXT.md`: the compare endpoint now returns `css` (top-level) and per-model `sections: [{heading, html}]`; the UI renders each section in an isolated iframe with `resume.css` and equalizes paired row heights. Reference: `docs/superpowers/specs/2026-06-29-resume-compare-section-alignment-design.md`.

- [ ] **Step 4: Commit**

```bash
git add react-dashboard/CONTEXT.md web/CONTEXT.md
git commit -m "[docs] Document section-aligned Resume Compare rendering"
```

---

## Self-Review

**Spec coverage:**
- Iframe + `resume.css` fidelity mechanism → Task 4 (cell rendering), Task 3 (css in response). ✓
- Backend pandoc → HTML, split at `<h2>`, "Header" leading section → Task 1 (`markdown_to_html`), Task 2 (`_split_sections_html`). ✓
- Per-model `sections`, top-level `css`, back-compat fields → Task 3. ✓
- Union of headings, case-insensitive match, model1-order-then-model2 → Task 4 `buildRows`. ✓
- Missing-section placeholder, errored-model handling, sticky scores header → Task 4. ✓
- Row-height equalization to max of pair → Task 4 `equalize`. ✓
- Tests for split (header/multi/no-h2), response shape, frontend rows/placeholder/scores → Tasks 2, 3, 4. ✓
- No DB/schema/template changes → honored. ✓

**Placeholder scan:** No TBD/TODO; all code steps contain full code. ✓

**Type consistency:** `markdown_to_html(str)->str`, `_split_sections_html(str)->list[{heading,html}]`, response `{css, model1{sections}, model2{sections}}`, frontend `buildRows(m1,m2)`, `srcDoc(css,html)`, `equalize(rowKey)`, `register(rowKey, side)` — consistent across tasks. ✓
