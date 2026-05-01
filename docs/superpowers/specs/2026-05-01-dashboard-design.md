# Dashboard Design Spec
**Date:** 2026-05-01

## Overview

Replace the existing Review Queue with a full-featured job dashboard as the app's landing page. The dashboard lists all jobs in the database, supports sorting, and provides a details overlay for each job with actions for scoring, generation, viewing, and state transitions.

## Tech Stack

- **Backend:** FastAPI (existing)
- **Frontend:** Vanilla HTML/CSS + Alpine.js (loaded via CDN script tag, no build step)
- **State management:** Alpine.js `x-data` reactive state (client-side)
- **No new Python dependencies**

## State Machine Simplification

The existing states (`scraped`, `scored`, `pending_review`, `approved`, `generated`) are retired and replaced with a single default state: `pending`.

| State | Color | Meaning |
|---|---|---|
| `pending` | Light gray | Default state for all new jobs |
| `applied` | Green | Application submitted |
| `rejected` | Red | Application rejected by employer |
| `failed` | Orange | Application failed (technical/process error) |

**Implications:**
- `core/types.py` — `JobState` enum updated to: `pending`, `applied`, `rejected`, `failed`
- `core/scorer.py` — scoring no longer transitions state; job stays `pending` after scoring
- `db/models.py` — default state value changed to `pending`
- DB migration required: existing jobs with retired states mapped to `pending` (or `applied` if state was `applied`)

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

**Score color-coding:** Green (≥ 0.8), Amber (0.5–0.8), Red (< 0.5)

**Status color-coding:** See state machine table above.

**Data loading:** On page load, Alpine fetches `GET /api/jobs` with no state filter, returning all jobs.

## Details Overlay

Triggered by clicking any table row. Layout:

```
Title                                    Status (color-coded)
Company | Score | Location | Salary
[ actions ]
─────────────────────────────────────────
Description (full text, scrollable)
```

**Score** in overlay is color-coded identically to the table.
**Status** in overlay is color-coded per the state machine table.
**Description** is full text, not truncated, scrollable if long.

### Action Bar

Fixed buttons (always visible):
- **Calculate Score** — triggers scoring via backend; updates score fields client-side on response
- **View Posting** — opens `job.url` in a new tab
- **Mark as Applied** — transitions job state to `applied`; updates status in table and overlay client-side
- **Delete** — two-step confirmation: click → becomes "Confirm Delete" → click → hard deletes job, closes overlay, removes row. Clicking anywhere else resets to "Delete."

Conditional buttons based on artifact state:

| Artifact state | Resume button | Cover button |
|---|---|---|
| No resume, no cover | `[ Generate Resume ]` | `[ Generate Cover Letter ]` |
| Resume only | `[ View Resume ▾ ]` | `[ Generate Cover Letter ]` |
| Cover only | `[ Generate Resume ]` | `[ View Cover Letter ▾ ]` |
| Both exist | `[ View Resume ▾ ]` | `[ View Cover Letter ▾ ]` |

The `▾` buttons are dropdowns with two options: **View** and **Regenerate**.

"Regenerate" hits the same endpoint as "Generate" — the generator overwrites the existing file.

On successful generate: `resume_path` / `cover_path` on the job object is updated client-side; button state updates immediately.

On successful delete: overlay closes, row is removed from the table client-side.

## Backend Endpoints

### Modified
- `GET /api/jobs` — remove state filter; return all jobs

### New
| Method | Path | Purpose |
|---|---|---|
| `DELETE` | `/api/jobs/{job_key}` | Hard delete job from DB |
| `POST` | `/api/jobs/{job_key}/score` | Run scorer on job; returns updated score fields |
| `POST` | `/api/jobs/{job_key}/generate/resume` | Trigger resume generation; returns updated `resume_path` |
| `POST` | `/api/jobs/{job_key}/generate/cover` | Trigger cover letter generation; returns updated `cover_path` |
| `GET` | `/api/jobs/{job_key}/resume` | Serve resume PDF |
| `GET` | `/api/jobs/{job_key}/cover` | Serve cover letter PDF |
| `PATCH` | `/api/jobs/{job_key}/state` | Transition state (used for `applied`) |

### Removed
- Old `PATCH /api/jobs/{job_key}/state` approve/reject logic is replaced by the new endpoint above, scoped only to `applied` transitions.

## File Changes

```
web/
├── main.py              # add DELETE, score, generate, and file-serve routes
├── routers/
│   └── jobs.py          # modify GET /api/jobs; add new endpoints
├── static/
│   ├── index.html       # full rewrite — Alpine.js dashboard
│   └── style.css        # full rewrite — table layout, overlay, action bar
└── CONTEXT.md           # create — documents known issues and future goals

core/
└── types.py             # update JobState enum

db/
└── models.py            # update default state value; migration for existing rows
```

No changes to `generator/` or `scraper/`.

## Future Goals (Out of Scope)

- Grouping rows by job title
- Clustering by location
- Config page
- Browser extension auto-detects application submission and marks job as applied (see browser-extension/CONTEXT.md)
