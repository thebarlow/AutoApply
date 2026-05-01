# Dashboard Design Spec
**Date:** 2026-05-01

## Overview

Replace the existing Review Queue with a full-featured job dashboard as the app's landing page. The dashboard lists all jobs in the database, supports sorting, and provides a details overlay for each job with actions for generation, viewing, and deletion.

## Tech Stack

- **Backend:** FastAPI (existing)
- **Frontend:** Vanilla HTML/CSS + Alpine.js (loaded via CDN script tag, no build step)
- **State management:** Alpine.js `x-data` reactive state (client-side)
- **No new Python dependencies**

## Page Structure

The dashboard is the only page. The nav bar remains at the top with the "Dashboard" link active. The "Review Queue" link is removed. "Config" remains as a placeholder.

The page has two layers:
1. **Table layer** — always visible, full-width job list
2. **Overlay layer** — details widget rendered on top when a row is clicked; dismissed by clicking outside or pressing Escape

Alpine.js manages all client-side state: selected job, sort column, sort direction, and the jobs array.

## Job Table

**Columns:** Title | Company | Score | Location | Salary | Status

**Sorting:**
- Sortable columns: Score, Salary, Status
- Clicking a column header sorts ascending; clicking again reverses to descending
- Sort is client-side — Alpine re-orders the in-memory jobs array, no server round-trip
- Score: numeric sort
- Salary: numeric if parseable, lexicographic otherwise (raw string in DB)
- Status: alphabetic (naturally groups same-status jobs)

**Score color-coding:** Green (≥ 0.8), Amber (0.5–0.8), Red (< 0.5) — consistent with former review queue

**Data loading:** On page load, Alpine fetches `GET /api/jobs` with no state filter, returning all jobs.

## Details Overlay

Triggered by clicking any table row. Layout:

```
Title                                    Status
Company | Score | Location | Salary
[ actions ]
─────────────────────────────────────────
Description (full text, scrollable)
```

**Score** in overlay is color-coded identically to the table.
**Description** is full text, not truncated, scrollable if long.

### Action Bar

Button states depend on whether `resume_path` and `cover_path` are set on the job:

| Artifact state | Buttons shown |
|---|---|
| No resume, no cover | `[ Generate Resume ] [ Generate Cover Letter ] [ View Posting ] [ Delete ]` |
| Resume only | `[ View Resume ▾ ] [ Generate Cover Letter ] [ View Posting ] [ Delete ]` |
| Cover only | `[ Generate Resume ] [ View Cover Letter ▾ ] [ View Posting ] [ Delete ]` |
| Both exist | `[ View Resume ▾ ] [ View Cover Letter ▾ ] [ View Posting ] [ Delete ]` |

The `▾` buttons are dropdowns with two options: **View** and **Regenerate**.

"Regenerate" hits the same endpoint as "Generate" — the generator overwrites the existing file.

**Delete flow:** "Delete" → click → button becomes "Confirm Delete" → click → job is deleted. Clicking anywhere else resets the button to "Delete."

On successful delete: overlay closes, row is removed from the table client-side.

On successful generate: `resume_path` / `cover_path` on the job object is updated client-side; button state updates immediately.

## Backend Endpoints

### Modified
- `GET /api/jobs` — remove `state=pending_review` filter; return all jobs

### New
| Method | Path | Purpose |
|---|---|---|
| `DELETE` | `/api/jobs/{job_key}` | Hard delete job from DB |
| `POST` | `/api/jobs/{job_key}/generate/resume` | Trigger resume generation; returns updated `resume_path` |
| `POST` | `/api/jobs/{job_key}/generate/cover` | Trigger cover letter generation; returns updated `cover_path` |
| `GET` | `/api/jobs/{job_key}/resume` | Serve resume PDF |
| `GET` | `/api/jobs/{job_key}/cover` | Serve cover letter PDF |

Generation endpoints call into `generator/generator.py`. The PATCH state endpoint is removed (state transitions are now implicit: generate = approve path, delete = reject path).

## File Changes

```
web/
├── main.py              # add DELETE, generate, and file-serve routes
├── routers/
│   └── jobs.py          # modify GET /api/jobs; add new endpoints
├── static/
│   ├── index.html       # full rewrite — Alpine.js dashboard
│   └── style.css        # full rewrite — table layout, overlay, action bar
└── CONTEXT.md           # create — documents known issues and future goals
```

No changes to `generator/`, `core/`, `db/`, or `scraper/`.

## Future Goals (Out of Scope)

- Grouping rows by job title
- Clustering by location
- Config page
- Application tracking
