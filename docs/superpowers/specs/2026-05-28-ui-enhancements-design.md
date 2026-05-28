# UI Enhancements — Design Spec

**Date:** 2026-05-28

## Overview

Four features: navbar logo, onboarding welcome message, manual job upload with job editing, and in-browser document editing with side-by-side PDF preview.

---

## 1. Navbar Logo

**File:** `react-dashboard/src/components/Navbar.jsx`

The existing `<Link to="/">` element contains only the text "Auto Apply". Augment it to include `<img src="/static/images/favicon-32x32.png" />` to the left of the text, with a small gap between image and text. No new component, no new route, no new asset.

---

## 2. Welcome Message in Onboarding Wizard

**File:** `react-dashboard/src/components/Onboarding/Wizard.jsx`

Add a welcome block at the top of the modal container, above the step indicator (`Step 1 of 2`). Content:

- Heading: **"Welcome to Auto Apply"**
- Subtitle: **"Streamlining your job search"**

Appears on both steps since it lives in the modal wrapper, not inside `StepLLM`.

---

## 3. Manual Job Upload + Job Field Editing

### 3a. Upload Button (Pipeline Inbox)

**Files:** `react-dashboard/src/components/widgets/Pipeline.jsx`

- An "Upload" button appears in the Inbox tab header, alongside the sort/search controls.
- Clicking opens an inline modal with the following fields:
  - **Title** (required, text input)
  - **Description** (required, textarea)
  - **Company** (optional, text input)
  - **Location** (optional, text input)
  - **Salary** (optional, text input)
  - **Job URL** (optional, text input — used as the dedup key and for the "View Post" button)
- On submit, the frontend calls `POST /api/scraper/stage-job` with:
  - `source: "manual"`
  - `job_key: "manual_<uuid>"`
  - `url: <provided URL> || "manual://<uuid>"`
  - All other provided fields
- No new backend endpoint. The existing `stage-job` handler runs `job.intake()` and spawns `run_pipeline` in a background thread — description extraction then scoring — identical to the browser extension flow.
- A new `uploadJob(fields)` helper is added to `api.js`.

### 3b. Job Field Edit Button (PreviewTab)

**Files:** `react-dashboard/src/components/widgets/Settings.jsx`, `web/routers/jobs.py`

- An "Edit" button appears in `PreviewTab` next to the existing "Delete" button in the content tab bar.
- Clicking opens a modal pre-populated with the job's current: Title, Description, Company, Location, Salary, URL.
- On save, calls `PATCH /api/jobs/{job_key}/fields` — a new endpoint that accepts a partial body of those six fields, updates the `Job` row, commits, and emits the updated job over SSE.
- Works for all jobs (manual or scraped).

**New backend endpoint:**

```
PATCH /api/jobs/{job_key}/fields
Body: { title?, description?, company?, location?, salary?, url? }
Returns: serialized Job
```

---

## 4. In-Browser Document Editing (Side-by-Side)

### Frontend

**File:** `react-dashboard/src/components/widgets/Settings.jsx`

- An "Edit" button is added to the toolbar of the resume and cover letter content tabs (visible in both Markdown and PDF sub-views).
- Clicking "Edit" opens a **full-viewport overlay** (z-index above Navbar).
- The overlay layout:
  - **Left column:** markdown `textarea` (raw source, fetched from existing `GET /api/jobs/{job_key}/resume/markdown` or `/cover/markdown`)
  - **Right column:** PDF `iframe` (showing the last-rendered PDF via existing `GET /api/jobs/{job_key}/resume` or `/cover`)
- Toolbar in overlay: **Save** button, **Close** button (×).
- **Save:** calls `PUT /api/jobs/{job_key}/resume/markdown` (or `/cover/markdown`) with the textarea content as `text/plain` body. On success, bumps the artifact nonce to reload the PDF iframe.
- **Close:** if `dirty` (textarea differs from originally fetched content), shows a confirmation modal — "You have unsaved changes. Discard them?" with Discard / Keep Editing buttons. If not dirty or user confirms, closes overlay.
- **Unsaved changes guard** fires on Close button click and Escape key. Since the overlay is full-viewport, tab switching and job switching are not possible while it's open.

### Backend

**File:** `web/routers/jobs.py`

Two new endpoints:

```
PUT /api/jobs/{job_key}/resume/markdown
Content-Type: text/plain
Body: <markdown string>

PUT /api/jobs/{job_key}/cover/markdown
Content-Type: text/plain
Body: <markdown string>
```

Each endpoint:
1. Validates the job exists.
2. Resolves the `.md` path: `generator/outputs/{job_key}_resume.md` or `{job_key}_cover.md`.
3. Writes the content to disk.
4. Calls the existing `job.generate_resume_pdf(_RESUME_TEMPLATE, db)` or `job.generate_cover_pdf(_COVER_TEMPLATE, db)` to re-render.
5. Updates `resume_generated_at` / `cover_generated_at` timestamp.
6. Commits, emits SSE, returns serialized job.

---

## Data Flow Summary

```
Upload button → stage-job API → run_pipeline (background) → SSE → Pipeline updates
Edit fields button → PATCH /api/jobs/{key}/fields → SSE → PreviewTab updates
Edit doc overlay → PUT /api/jobs/{key}/{type}/markdown → re-render PDF → nonce bump → iframe reloads
```

---

## Files Changed

| File | Change |
|---|---|
| `react-dashboard/src/components/Navbar.jsx` | Add favicon img to logo link |
| `react-dashboard/src/components/Onboarding/Wizard.jsx` | Add welcome heading above step indicator |
| `react-dashboard/src/components/widgets/Pipeline.jsx` | Add Upload button + upload modal |
| `react-dashboard/src/components/widgets/Settings.jsx` | Add Edit fields button + edit doc overlay + unsaved-changes guard |
| `react-dashboard/src/api.js` | Add `uploadJob`, `updateJobFields`, `putDocumentMarkdown` helpers |
| `web/routers/jobs.py` | Add `PATCH /{job_key}/fields`, `PUT /{job_key}/resume/markdown`, `PUT /{job_key}/cover/markdown` |
