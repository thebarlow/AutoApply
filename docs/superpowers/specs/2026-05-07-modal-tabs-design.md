# Job Details Modal — Tabbed Redesign

**Date:** 2026-05-07  
**Branch:** feat-dashboard-modal

---

## Layout

```
┌─────────────────────────────────────────────┐
│ Header (title, status badge, spinner)        │
│ Meta (company, score, location, salary)      │
│ Action bar                                   │
├───────────────┬─────────────────────────────┤
│ Overview      │                             │
│ Resume        │   Tab content               │
│ Cover Letter  │                             │
│               │                             │
└───────────────┴─────────────────────────────┘
```

Below the action bar the panel splits into two columns: a narrow left sidebar containing the vertical tab selectors, and a main content area on the right. The MD/PDF toggle pill lives inside the tab content area (top of Resume or Cover Letter content), not on the selector itself.

---

## Tabs

### Overview (default)
- Displays the job description (current `overlay-description` content).

### Resume
- **No resume generated:** Shows an empty state with a "Generate Resume" button (this button also appears in the action bar — both trigger the same action).
- **Resume exists, MD view (default):** Fetches and renders markdown content inline. Provides a MD | PDF toggle pill at the top of the tab content.
- **Resume exists, PDF view:** Renders the PDF via `<iframe>` pointed at the existing `/api/jobs/{key}/resume` endpoint.

### Cover Letter
- Identical structure to Resume tab.
- Generate is blocked (button disabled + tooltip) if no resume exists yet — preserving the existing constraint.

---

## Action Bar

Split into **tab-specific actions** (left) and **persistent actions** (right).

| Active Tab | Tab-specific actions (left) | Persistent actions (right) |
|---|---|---|
| Overview | Calculate Score | View Posting · Mark Applied · Delete Job |
| Resume — no resume | Generate Resume | View Posting · Mark Applied · Delete Job |
| Resume — has resume | View Prompt · Regenerate · Delete Resume | View Posting · Mark Applied · Delete Job |
| Cover — no cover | Generate Cover Letter | View Posting · Mark Applied · Delete Job |
| Cover — has cover | View Prompt · Regenerate · Delete Cover | View Posting · Mark Applied · Delete Job |

Delete Job remains in persistent actions on all tabs. Delete Resume / Delete Cover are tab-specific and only remove the generated file, not the job record.

---

## View Prompt Overlay

Clicking "View Prompt" opens a lightweight overlay inside the modal (darkened backdrop, scrollable `<pre>` block, close button). The prompt is fetched on demand from the backend — it is not stored, just reconstructed from the current template + job data.

---

## New Backend Endpoints

All added to `web/routers/jobs.py`:

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/{key}/resume/markdown` | Return `.md` file content as `text/plain` |
| `GET` | `/{key}/cover/markdown` | Return `.md` file content as `text/plain` |
| `GET` | `/{key}/resume/prompt` | Reconstruct and return resume prompt as `text/plain` |
| `GET` | `/{key}/cover/prompt` | Reconstruct and return cover prompt as `text/plain` |
| `DELETE` | `/{key}/resume` | Delete resume file, clear `job.resume_path` |
| `DELETE` | `/{key}/cover` | Delete cover file, clear `job.cover_path` |

The prompt endpoints call the existing `build_resume_prompt` / `build_cover_prompt` functions from `generator/generator.py` using the live DB state — no new generator logic needed.

---

## Frontend State (Alpine.js)

New state fields added to the `dashboard()` component:

```js
activeTab: 'overview',        // 'overview' | 'resume' | 'cover'
resumeView: 'md',             // 'md' | 'pdf'
coverView: 'md',              // 'md' | 'pdf'
resumeMarkdown: null,         // fetched string or null
coverMarkdown: null,          // fetched string or null
promptOverlay: null,          // null | { type: 'resume'|'cover', text: string }
```

Tab switch resets the relevant view to `'md'` and clears cached markdown so it re-fetches. Markdown is fetched once per tab visit and cached until the overlay closes or a regeneration occurs.

---

## Files Changed

| File | Change |
|---|---|
| `web/routers/jobs.py` | Add 6 new endpoints |
| `web/static/index.html` | Refactor overlay HTML + Alpine state/methods |
| `web/static/style.css` | Add tab, toggle-pill, prompt-overlay styles |
