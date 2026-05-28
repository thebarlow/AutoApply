# Design: Misc Dashboard & Server Features
**Date:** 2026-05-27
**Branch:** misc-features

---

## 1. User Profile — Empty Section Markers

### What
Accordion section headers in `ProfileDetail.jsx` display a gray `[empty]` badge when the section has no meaningful content.

### Empty conditions per section

| Section | Empty when |
|---|---|
| Identity | all text fields are blank strings |
| Skills | `skills` array length === 0 |
| Experience | `experience` array length === 0 |
| Education | `education` array length === 0 |
| Projects | `projects` array length === 0 |
| Job Prefs | `target_roles` blank AND salary min/max unset |
| Prompts | never (always has defaults) |
| LLM | never (always has a provider) |

### Implementation
- Add `isSectionEmpty(section, profile)` helper inside `ProfileDetail.jsx`.
- Accordion trigger label renders `<span className="empty-badge">[empty]</span>` inline when condition is met.
- No backend changes required.

---

## 2. User Profile — Export Master Button

### What
A button "Export Master" in `ProfileDetail.jsx`, positioned between the last accordion section and the Delete button. Generates a multi-page master resume PDF from the current profile with no LLM call.

### Frontend
- Button calls `POST /api/profile/export-master`.
- On success, receives a PDF blob and triggers a browser download as `master_resume.pdf`.
- Shows a loading spinner on the button during the request.

### Backend
- New endpoint: `POST /api/profile/export-master` in `web/routers/config.py`.
- Reads the active profile from DB.
- Renders a new Markdown template `generator/master_resume_template.md` with all profile sections substituted in (Jinja2 or simple string formatting).
- Shells out to `pandoc`/`xelatex` (same approach as existing resume pipeline) to produce the PDF.
- No page limit enforced — all sections included regardless of length.
- Returns the PDF as `application/pdf` with `Content-Disposition: attachment; filename="master_resume.pdf"`.

### Template
`generator/master_resume_template.md` — new file. Includes all sections: identity, skills, experience, education, projects, job preferences. Empty sections are omitted from output.

---

## 3. Navbar — "Help" Rename

One-line change: the `?` link text in `Navbar.jsx` becomes `Help`. Same href, no other changes.

---

## 4. Navbar — Session Cost

### What
Replaces the hardcoded "Credits: $0.00" in the navbar with a live "Session Cost" counter that accumulates actual cost from LLM responses. Resets to $0.00 on every server start. Clicking opens a modal with 8 decimal place precision.

### Backend — `core/session_cost.py` (new file)
- Thread-safe in-memory float accumulator using `threading.Lock`.
- `add_cost(cost: float)` — adds to the total.
- `get_total() -> float` — returns current total.
- Cost extracted from LLM response objects: check `response.usage` for a `cost` field (OpenRouter native). If absent, cost contribution is `0.0` (silent, no error).

### Backend — `core/llm.py` changes
- `call_llm()` captures the full response object before extracting text.
- After the call: `session_cost.add_cost(getattr(response.usage, 'cost', 0.0))`.
- All direct `client.chat.completions.create()` callers (scorer, extractor) updated the same way.

### Backend — new endpoint
- `GET /api/session-cost` → `{ "total": float }` in `web/routers/` (new small router or added to an existing one).

### Frontend
- Navbar polls `GET /api/session-cost` every 5 seconds.
- Displays `Session Cost: $X.XX` (2 decimal places).
- Click opens a modal: full value at 8 decimal places, dismisses on outside click or Escape.

---

## 5. Navbar — Power Button (Shutdown)

### What
A red circular power icon at the right end of the navbar. Shuts down the entire app (FastAPI server + tray). Handles in-flight LLM calls gracefully.

### Frontend — power icon
- SVG power icon: red circle outline with a vertical line through the top (standard power symbol).
- On click:
  1. Calls `GET /api/llm-status` (existing endpoint).
  2. If no in-flight calls → calls `POST /api/shutdown?mode=immediate` directly.
  3. If in-flight calls → shows a dropdown/popover listing each call as `{job_title} | {company}` (one row per call), with two action buttons:
     - **Exit Now** → `POST /api/shutdown?mode=immediate`
     - **Exit After LLM Completes** → `POST /api/shutdown?mode=wait`

### Backend — `web/routers/shutdown.py` (new router)
- `POST /api/shutdown?mode=immediate|wait`
- `immediate`: schedules `os._exit(0)` in a background thread with 300ms delay (lets HTTP response send first). Returns `{ "ok": true }`.
- `wait`: launches a background task that polls `llm_status.get_all()` every 1 second until all in-flight calls are done, then calls `os._exit(0)`. Returns `{ "ok": true, "mode": "wait" }` immediately.

### Backend — LLM status enrichment
- `/api/llm-status` response enriched to include `job_title` and `company` for each in-flight entry by joining against the jobs table (single DB query keyed by job_key).

### Tray app exit
- `tray_app/main.py` adds a heartbeat: every 2 seconds it pings `GET /health` (or any fast endpoint). If the server becomes unreachable (connection refused or timeout), the tray app calls `QApplication.quit()` and exits cleanly.
- No IPC required — tray exits naturally when server dies.

---

## Files Changed

| File | Change |
|---|---|
| `react-dashboard/src/components/ProfileDetail.jsx` | Empty badges, Export Master button |
| `react-dashboard/src/components/Navbar.jsx` | Help rename, Session Cost display + modal, Power button |
| `core/session_cost.py` | New — in-memory cost accumulator |
| `core/llm.py` | Capture response.usage.cost, call session_cost.add_cost() |
| `core/job.py` | Update direct LLM callers (scorer, extractor) to track cost |
| `web/routers/config.py` | Add export-master endpoint |
| `web/routers/shutdown.py` | New — shutdown endpoint |
| `web/routers/llm_status_router.py` | Enrich response with job_title + company |
| `web/main.py` | Register shutdown router |
| `generator/master_resume_template.md` | New — master resume layout template |
| `tray_app/main.py` | Add server heartbeat → auto-exit when server dies |
