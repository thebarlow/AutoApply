---
title: Job Flagging, Cover Letter Double Intro Fix, Prompt Save As
date: 2026-05-28
status: approved
---

# Job Flagging, Cover Letter Double Intro Fix, Prompt Save As

## Overview

Three independent improvements:

1. **Job flagging** — users can mark a job with a red flag as a personal warning signal; visible on the job card and togglable in the preview pane.
2. **Cover letter double intro fix** — generated cover letters currently render two greeting lines (one from the template, one from the LLM). Fix by updating the prompt.
3. **Prompt Save As** — add a "Save As" button to the prompt editor so users can rename a prompt or save a copy under a chosen filename.

---

## 1. Job Flagging

### DB

Add `flagged` column to the `jobs` table:

- **Model** (`core/job.py`): `flagged = Column(Boolean, default=False)`
- **Migration** (`db/database.py`): new `_migrate_flagged_column()` function using the existing `ALTER TABLE` pattern; called from `init_db()`.

### API

New endpoint in `web/routers/jobs.py`:

```
PATCH /api/jobs/{job_key}/flag
Body: { "flagged": bool }
Response: serialized job (same shape as GET /api/jobs items)
```

After writing the DB change, broadcast the updated job via SSE (same pattern as state transitions). Add `flagged` to `_serialize()` so it appears on every job object the frontend receives.

### Frontend

**`api.js`**: add `flagJob(jobKey, flagged)` — `PATCH /api/jobs/{job_key}/flag` with `{ flagged }`.

**`JobCard.jsx`**: accept a `flagged` prop. When true, render a small filled red flag SVG in the right-side icon cluster (alongside the existing score pill and status icons). When false, render nothing (flag only shows on the card when active — it is set in the preview, not the card).

**`Settings.jsx` `PreviewTab` info block**: add a flag toggle button in the top info section, alongside the title/company/state row. The button renders an outline flag SVG when `flagged=false` and a filled red SVG when `flagged=true`. Clicking it calls `flagJob` optimistically and lets SSE confirm the update. No spinner — it's a fast local write.

**`Pipeline.jsx`**: pass `flagged={job.flagged}` down to `JobCard`.

---

## 2. Cover Letter Double Intro Fix

### Root Cause

`generator/cover_template.html:56` always renders:

```html
<p class="cover-greeting">To the hiring team at {{ company }},</p>
```

The current `prompts/defaults/cover.md` prompt instructs the LLM to "Address it to the hiring team at {job.company}" without telling it that greeting is already injected. The LLM therefore opens its output with its own salutation (e.g. "Dear Hiring Team at…"), producing two intro lines in the final PDF.

### Fix

Add one instruction line to `prompts/defaults/cover.md`, consistent with the existing sign-off exclusion:

```
- Do not include a greeting or salutation line (e.g. "Dear Hiring Team...") — it is prepended automatically.
```

Remove the "Address it to the hiring team at {job.company}" instruction, since the template already handles the addressee.

No code changes required. The fix is prompt-only and takes effect on the next generation.

---

## 3. Prompt Save As

### Problem

The current Save flow for non-default files overwrites in-place; for default files it auto-forks with a `{basename}_{timestamp}.md` name. Neither lets the user choose the output filename.

### Solution

Add a **Save As** button to the `PromptModal` footer in `ProfileDetail.jsx`. Behavior:

1. Clicking "Save As" reveals an inline text input pre-filled with `{current_basename}_copy.md` (or `{typeKey}_custom.md` if the current file is a default).
2. User edits the name and clicks "Save As" (confirm) or presses Escape to cancel.
3. On confirm: call `POST /api/prompts/file` (`createPromptFile`) with the user-supplied filename and current editor content. On success, set the new file as `selectedFile`, update `originalContent`, and save the profile link via `updateProfile` (same as the normal save path).
4. If the filename already exists the backend returns 409 — surface it as an inline error next to the input ("A file with that name already exists").

No new backend endpoints required. `POST /api/prompts/file` already enforces uniqueness and returns file metadata.

### UI Layout

Footer before Save As is clicked:
```
[ Save As ]  [ Save ]  [ Cancel ]
```

Footer after Save As is clicked (inline expansion):
```
Filename: [___________________]  [ Confirm ]  [ ✕ ]
```

The main Save button remains available while the Save As input is open.

---

## Affected Files

| File | Change |
|------|--------|
| `core/job.py` | Add `flagged` column to `Job` model |
| `db/database.py` | Add `_migrate_flagged_column()`; call from `init_db()` |
| `web/routers/jobs.py` | Add `PATCH /flag` endpoint; add `flagged` to `_serialize()` |
| `react-dashboard/src/api.js` | Add `flagJob()` |
| `react-dashboard/src/components/shared/JobCard.jsx` | Add `flagged` prop + flag icon |
| `react-dashboard/src/components/widgets/Pipeline.jsx` | Pass `flagged` to `JobCard` |
| `react-dashboard/src/components/widgets/Settings.jsx` | Add flag toggle in `PreviewTab` info block |
| `prompts/defaults/cover.md` | Fix double greeting instruction |
| `react-dashboard/src/components/widgets/ProfileDetail.jsx` | Add Save As UI to `PromptModal` |
