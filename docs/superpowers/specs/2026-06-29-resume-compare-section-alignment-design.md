# Resume Compare — Section-Aligned, PDF-Styled View

**Date:** 2026-06-29
**Status:** Approved (design)
**Area:** Admin panel → Resume Compare harness (`react-dashboard/src/components/admin/ResumeCompare.jsx`, `web/routers/dev.py`)

## Problem

The admin Resume Compare harness runs two résumé generators (Model 1 single-call,
Model 2 per-section) for a job and shows both as free-flowing Markdown columns. Two
problems:

1. **Sections don't line up.** Because each column flows independently and sections
   have variable lengths, comparing the same section across models requires manual
   scrolling/scanning.
2. **No PDF fidelity.** Markdown is rendered with the dashboard's dark `prose` theme,
   not the résumé's actual print styling, so it's hard to judge how a section will
   actually look in the delivered PDF.

## Goals

- Compare the two résumés **section by section, aligned in rows**, so the same
  section sits at the same vertical position across both models regardless of length.
- Render each section **as it would appear in the PDF** — using the real
  `generator/resume.css` styling, isolated from the dashboard theme.

## Non-Goals

- Generating real `.pdf` files or embedding them (no headless-Chromium path).
- Zoom controls.
- Item-level alignment (per-experience / per-project entry matching across models).
- Per-section collapse toggles.
- Textual diff highlighting between the two cells.

## Design

### Fidelity mechanism

Each section cell renders inside its own **iframe** that carries the contents of
`generator/resume.css`. This gives:

- True PDF visual fidelity (serif ALL-CAPS section headers, Helvetica body, white
  page, `pt` sizing) — the same CSS the PDF pipeline uses.
- Full CSS isolation: `resume.css` targets `html, body` and `.resume`-scoped
  selectors with light backgrounds, which would clash with the dashboard's dark
  theme if injected directly. An iframe sandboxes it.

No Chromium and no `.pdf` files are involved — only pandoc (already a dependency)
plus the existing CSS.

### Backend — `web/routers/dev.py`

Current `run_comparison` returns, per model, `{ markdown, score, ... }` or
`{ error }`. Extend it:

1. After producing each model's assembled Markdown, run **one pandoc pass**
   Markdown → HTML fragment, reusing the pandoc invocation already used by
   `core/utils.py` `render_pdf` (factor out a small `markdown_to_html(md) -> str`
   helper if one does not already exist; otherwise call the existing path).
2. Split the HTML into sections with a new helper
   `_split_sections_html(html) -> list[dict]`:
   - Split at each top-level `<h2 ...>` boundary. Each section dict is
     `{ "heading": <text of the h2, stripped>, "html": <h2 + following content up
     to next h2> }`.
   - Any content **before the first `<h2>`** (name/contact header — notably the
     tree-v1 Model 2 output, which emits the name as `<h1>` and contact as the
     following `<p>`) becomes a leading section with `heading = "Header"`.
   - If there are no `<h2>` elements, return a single `{ "heading": "Header",
     "html": <full fragment> }`.
3. Per-model result gains `sections: [{heading, html}, ...]`. Existing `markdown`
   and `score` (and `error`) fields are unchanged for back-compat.
4. The top-level response gains `css: <contents of generator/resume.css>` read once
   per request (small file; simple read is fine).

Error case: when a model returns `{ error }`, it has no `sections`; the response
still includes `css`. The frontend treats a model with no `sections` as errored.

#### Backend return shape

```json
{
  "css": "@page { ... } ...",
  "model1": {
    "score": 0.87,
    "markdown": "## Profile\n...",
    "sections": [
      { "heading": "Header",  "html": "<h1>Jane Doe</h1><p>...</p>" },
      { "heading": "Profile", "html": "<h2 id=\"profile\">Profile</h2><p>...</p>" }
    ]
  },
  "model2": { "score": 0.83, "markdown": "...", "sections": [ ... ] },
}
```

(On per-model failure the model object is `{ "error": "..." }` with no `sections`.)

### Frontend — `ResumeCompare.jsx`

Replace the two free-flowing `<Column>` components with a two-column aligned grid.

**Heading union & ordering.** Build the ordered list of rows from the union of both
models' section headings, matched **case-insensitively** (trimmed). Order = Model 1's
section order, then any headings present only in Model 2 appended in their Model 2
order. Each row maps to `{ heading, model1Section | null, model2Section | null }`.

**Rendering a cell.**
- If the section exists for that model: an `<iframe>` whose `srcDoc` is
  `<style>${css}</style><div class="resume">${section.html}</div>`.
- If absent: a muted "— not present —" placeholder (keeps the row aligned).
- If the whole model errored (`model.error`): the model's entire column shows the
  error message (same as today), and the grid is not rendered for that model.
  (If only one model errored, still render the grid for the other, with the errored
  side showing the error in place of cells. Implementation may choose the simpler
  path of showing the error banner above and skipping the grid if **either** model
  errored — acceptable, but preferred behavior is to still show the healthy side.)

**Row-height alignment.** After each iframe loads, measure its content height
(`iframe.contentDocument.documentElement.scrollHeight`) and set the iframe's height.
For each row, set both iframes' heights to the **max** of the pair so the next
section's headings line up across both columns. Re-measure on result change. A small
`useLayoutEffect` / ref-map per row handles this; debounce or run once per load
event (no continuous observer needed since content is static after load).

**Header row.** Keep a sticky top row with the two model titles and eval scores
(`score N.NN`), as today.

### Files touched

| File | Change |
|---|---|
| `web/routers/dev.py` | Add `_split_sections_html`; add `markdown_to_html` use; include `sections` per model + top-level `css`. |
| `core/utils.py` | (Only if needed) expose a `markdown_to_html` helper factored from `render_pdf`'s pandoc step. |
| `tests/web/test_resume_compare.py` | Unit-test `_split_sections_html` (header pre-content, multiple `<h2>`, no `<h2>`); assert response includes `sections` + `css`. |
| `react-dashboard/src/components/admin/ResumeCompare.jsx` | Replace `Column` with aligned two-column section grid + iframe cells + row-height equalization. |
| `react-dashboard/src/components/admin/ResumeCompare.test.jsx` | Update for new structure (rows per heading, placeholder for missing, scores in header row). |

No DB, schema, prompt, or generator-template changes.

## Testing

- **Backend unit:** `_split_sections_html` for: content before first `<h2>` →
  "Header" row; multiple `<h2>` sections split correctly with heading text; no
  `<h2>` → single "Header" section. Response shape includes `css` and per-model
  `sections`; errored model still yields top-level `css`.
- **Frontend:** rows built from the union of headings; case-insensitive matching;
  Model-2-only heading appended after Model-1 order; missing section shows
  placeholder; iframe `srcDoc` includes the css and `.resume` wrapper; header row
  shows both scores. Mock `resumeCompare` from `../../api`.

## Risks / Tradeoffs

- **DOM weight:** one iframe per section per model (~10–12 iframes). Negligible for
  an admin-only dev harness with a handful of sections.
- **Height-equalization timing:** iframe `scrollHeight` is only reliable after load;
  the equalization runs on each iframe's `onload`. Static content means no observer
  is needed, but if a font loads late the measured height could be slightly off; the
  résumé CSS uses system fonts (Helvetica/Georgia), so this is not a concern.
- **Heading matching is by text:** if the two models title the same section
  differently (e.g. "Summary" vs "Profile"), they will appear as two separate rows.
  Acceptable — surfacing that divergence is itself useful signal in a compare tool.
