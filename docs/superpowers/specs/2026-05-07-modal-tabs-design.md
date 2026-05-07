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
Displays the job description (current `overlay-description` content).

### Resume
- **No MD, no PDF:** Empty state message in the content area.
- **MD exists, MD view (default):** Fetches and renders markdown content inline. Toggle pill (MD | PDF) at top of content area.
- **MD exists, PDF view:** `<iframe>` pointed at `/api/jobs/{key}/resume` (the existing PDF endpoint).
- **No MD but PDF somehow exists:** Show PDF view only (no toggle).

### Cover Letter
Identical structure to Resume tab. Generate PDF is blocked (disabled) if no resume PDF exists yet — preserving the existing constraint.

---

## Action Bar

Split into **tab-specific actions** (left) and **persistent actions** (right).

| Active Tab | State | Tab-specific actions (left) | Persistent (right) |
|---|---|---|---|
| Overview | — | Calculate Score | View Posting · Mark Applied · Delete Job |
| Resume | no MD, no PDF | Generate MD · Generate PDF (disabled) | View Posting · Mark Applied · Delete Job |
| Resume | MD exists, no PDF | Regenerate MD · Generate PDF · View Prompt | View Posting · Mark Applied · Delete Job |
| Resume | MD + PDF exist | Regenerate MD · Regenerate PDF · View Prompt | View Posting · Mark Applied · Delete Job |
| Cover | no MD, no PDF | Generate MD · Generate PDF (disabled) | View Posting · Mark Applied · Delete Job |
| Cover | MD exists, no PDF | Regenerate MD · Generate PDF · View Prompt | View Posting · Mark Applied · Delete Job |
| Cover | MD + PDF exist | Regenerate MD · Regenerate PDF · View Prompt | View Posting · Mark Applied · Delete Job |

"Generate MD" becomes "Regenerate MD" when an MD file already exists. Same pattern for PDF. Delete Resume / Delete Cover are not explicit buttons — regenerating overwrites the existing file. Delete Job remains in persistent actions on all tabs and removes the job record entirely.

---

## View Prompt Overlay

Clicking "View Prompt" opens a lightweight overlay inside the modal (darkened backdrop, scrollable `<pre>` block, close button). The prompt is fetched on demand — reconstructed server-side from the current template + job data, not stored.

---

## Backend Changes

### Jobs API response (`web/routers/jobs.py`)

The existing `GET /api/jobs` and `GET /api/jobs/{key}` responses gain two derived boolean fields — no DB migration needed, computed by checking file existence on disk:

```json
"resume_md_exists": true,
"cover_md_exists": false
```

MD paths are deterministic: `generator/outputs/{job_key}_resume.md` / `{job_key}_cover.md`.  
`resume_path` / `cover_path` continue to track the PDF paths as before.

### New endpoints (`web/routers/jobs.py`)

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/{key}/generate/resume/md` | Call `generate_resume_md()` from generator |
| `POST` | `/{key}/generate/resume/pdf` | Call `generate_resume_pdf()` from generator |
| `POST` | `/{key}/generate/cover/md` | Call `generate_cover_md()` from generator |
| `POST` | `/{key}/generate/cover/pdf` | Call `generate_cover_pdf()` from generator |
| `GET` | `/{key}/resume/markdown` | Return `.md` file content as `text/plain` |
| `GET` | `/{key}/cover/markdown` | Return `.md` file content as `text/plain` |
| `GET` | `/{key}/resume/prompt` | Reconstruct and return resume prompt as `text/plain` |
| `GET` | `/{key}/cover/prompt` | Reconstruct and return cover prompt as `text/plain` |

All four generate endpoints return the updated job object (same shape as existing generate endpoints). The existing `POST /{key}/generate/resume` and `POST /{key}/generate/cover` endpoints are kept for backwards compatibility but are no longer called by the dashboard.

Prompt endpoints call `build_resume_prompt` / `build_cover_prompt` from `generator/generator.py` using live DB state.

---

## Frontend State (Alpine.js)

New fields added to the `dashboard()` component:

```js
activeTab: 'overview',        // 'overview' | 'resume' | 'cover'
resumeView: 'md',             // 'md' | 'pdf'
coverView: 'md',              // 'md' | 'pdf'
resumeMarkdown: null,         // fetched string or null
coverMarkdown: null,          // fetched string or null
promptOverlay: null,          // null | { type: 'resume'|'cover', text: string }
generating: null,             // null | 'resume_md' | 'resume_pdf' | 'cover_md' | 'cover_pdf'
```

Tab switch resets the relevant view to `'md'` and clears cached markdown so it re-fetches on next visit. Markdown is fetched once per tab visit and cached until a regeneration occurs (which clears the cache and re-fetches).

---

## Files Changed

| File | Change |
|---|---|
| `web/routers/jobs.py` | Add `resume_md_exists`/`cover_md_exists` to job serialization; add 8 new endpoints |
| `web/static/index.html` | Refactor overlay HTML + Alpine state/methods |
| `web/static/style.css` | Add tab sidebar, toggle-pill, prompt-overlay styles |
