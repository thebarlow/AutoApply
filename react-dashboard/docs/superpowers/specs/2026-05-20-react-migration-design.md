# React Dashboard Migration Design

**Date:** 2026-05-20
**Status:** Approved

## Overview

Wire the existing `react-dashboard` Vite/React prototype to the FastAPI backend, replacing the current Alpine.js pages (dashboard, config, setup). The Help page is not touched. The prototype's space-themed dark UI is retained and extended.

---

## Serving Architecture

**Dev:** Vite dev server runs on `:5173`. `vite.config.js` proxies `/api/*` to `http://localhost:8080`, so API calls work without CORS issues.

**Production:** `npm run build` outputs to `react-dashboard/dist/`. FastAPI (`web/main.py`) is updated to:
- Mount `/assets` → `react-dashboard/dist/assets/` (Vite's compiled JS/CSS bundles)
- Serve `react-dashboard/dist/index.html` for `/`, `/config`, `/setup` and a catch-all for any unmatched non-API GET route

The old Alpine.js HTML files in `web/static/` are not deleted but are no longer routed to.

---

## State Machine Changes

**File:** `core/types.py`

New job states (replacing `draft` and `in_contact`):

| State | Meaning |
|---|---|
| `new` | Job just scraped, no user interaction yet |
| `pending_review` | Returned from a processing operation; awaiting human review |
| `ready` | Docs approved by user; queued to be submitted |
| `applied` | Application submitted |
| `contact` | Employer made contact (replaces `in_contact`) |
| `rejected` | Application rejected |

**DB migration required:** Existing rows with `state = 'draft'` → `new`. Rows with `state = 'in_contact'` → `contact`.

---

## Real-Time Updates (SSE)

**New FastAPI endpoint:** `GET /api/events` — an SSE stream.

**Event payload:** Full job object (same shape as a single item from `GET /api/jobs`) serialized as JSON. Fired on any job table write: insert or update.

**React behavior:** On page load, open an `EventSource` pointing at `/api/events`. On each event, upsert the received job into local state by `job_key` — no re-fetch needed. On connection error, fall back to a one-time re-fetch of `GET /api/jobs`.

**Where SSE is emitted:** The job router functions that write to the DB (`create_job`, `update_job_state`, post-generation handlers) broadcast via a shared in-memory channel. A simple `asyncio.Queue`-per-client pattern is sufficient; no external message broker needed.

---

## API Layer

**New file:** `react-dashboard/src/api.js`

Thin fetch wrappers — no raw `fetch` calls in components. All functions return parsed JSON or throw on non-ok response.

Functions needed:
- `getJobs()` → `GET /api/jobs`
- `getProfiles()` → `GET /api/config/profiles`
- `getProviders()` → `GET /api/config/providers`
- `getJobExtraction(jobKey)` → `GET /api/jobs/{key}/description?view=json`

---

## Pipeline Widget

**File:** `src/components/widgets/Pipeline.jsx`

### Layout

Four tabs across the top of the widget: **Inbox | Processing | Outbound | Archives**

Each tab shows a scrollable list of `JobCard` components filtered from shared job state.

### Tab filtering

| Tab | Filter |
|---|---|
| Inbox | `state === 'new' \|\| state === 'pending_review'` |
| Processing | `processingKeys.has(job.job_key)` (client-side Set) |
| Outbound | `state === 'ready'` |
| Archives | `state === 'applied' \|\| state === 'contact' \|\| state === 'rejected'` |

### Processing state

`processingKeys` is a `Set<string>` held in App-level state. When any API action is fired on a job (generate, score, etc.), the job's `job_key` is added. When the action resolves (success or error), it is removed. Jobs in `processingKeys` render in the Processing tab regardless of their DB state.

### Job card click

Clicking a `JobCard` calls `onJobSelect(job)` (prop from App), which sets `selectedJob` in App state and switches the Settings widget to the Preview tab.

---

## Settings Widget

**File:** `src/components/widgets/Settings.jsx`

### Tabs

**User | Tasks | Advanced | Preview**

Preview is the rightmost tab. It is visually dimmed and non-interactive when `selectedJob === null`. When a job is selected it activates automatically.

Pressing **Escape** or clicking outside the job card clears `selectedJob`, dimming Preview again and returning to whichever tab was previously active.

### Preview tab

**Header section:**
- Job title (large)
- Company, location, salary, score badge, status badge in a metadata row

**Divider**

**Description section:**
- Toggle button: **Raw** / **Extracted** (default: Raw)
- Raw: renders `selectedJob.description` as plain text
- Extracted: if `selectedJob.extraction_json_exists`, fetches `GET /api/jobs/{key}/description?view=json` and renders the parsed JSON as a formatted list; otherwise shows "No extraction yet."

### User tab

Fetches `GET /api/config/profiles` on mount. Renders a radio-selectable list of profiles. "Create Profile" sub-view (already built) posts to `POST /api/config/profiles`.

### Advanced tab

Fetches `GET /api/config/providers` on mount. Renders existing provider fields. Save calls `PUT /api/config/providers/{id}`.

### Tasks tab

Reads `processingKeys` from App state (passed as prop). Renders a list of in-flight job operations. Empty state: "No active tasks."

---

## App-Level State

`src/App.jsx` owns:

| State | Type | Purpose |
|---|---|---|
| `jobs` | `Job[]` | Full job list; updated by SSE upserts |
| `selectedJob` | `Job \| null` | Currently selected job for Preview tab |
| `processingKeys` | `Set<string>` | Jobs with in-flight API calls |
| `settingsTab` | `string` | Active Settings tab; set to `'Preview'` on job select |

---

## FastAPI Changes

**File:** `web/main.py`

1. Add SSE endpoint: `GET /api/events`
2. Mount `react-dashboard/dist/assets` at `/assets`
3. Change `/`, `/config`, `/setup` routes to serve `react-dashboard/dist/index.html`
4. Add catch-all: any non-API GET → `react-dashboard/dist/index.html`

**File:** `web/routers/jobs.py` (and any other router that writes jobs)
- After each DB write, publish the updated job object to the SSE broadcast channel.

---

## Vite Config

**File:** `react-dashboard/vite.config.js`

Add dev proxy:
```js
server: {
  proxy: {
    '/api': 'http://localhost:8080'
  }
}
```

---

## Out of Scope

- Job actions from the UI (generate resume, score, change status, delete) — Preview tab is read-only
- Full profile creation/editing beyond name + resume upload in the Create Profile sub-view
- Help page (untouched)
- Authentication
