# User Profile Config Section — Design Spec

**Date:** 2026-05-02
**Branch:** make-config

## Goal

Implement the User Profile section of the config page. Supports multiple named user profiles. Each profile can be created by uploading a PDF or Markdown resume, parsing it into structured fields, editing the result, and saving. One profile is designated as active at a time.

## Pipeline

```
PDF → Markdown → JSON → Database
```

For `.md` uploads, the PDF→Markdown stage is skipped.

## Architecture

### DB change: `UserProfileModel`

Add a `name` column (string, not null, default `"Default"`) to `UserProfileModel`. This is the display label for the profile (e.g. "Software Engineer", "Data Engineer"). Multiple rows are now supported — one per profile.

The active profile is tracked in the `Config` table under the key `active_profile_id` (stores the integer row ID), matching the pattern used by `llm_active_provider`.

A SQLAlchemy migration (via `db/migrations/` or inline `create_all` safe path) adds the column.

### New file: `core/profile_parser.py`

Two functions:

**`pdf_to_markdown(pdf_bytes: bytes) -> str`**
- Uses `pdfplumber` to extract text page by page
- Detects section headings via heuristics: ALL CAPS lines, or lines followed by a blank line → formatted as `## Heading`
- Bullet-like lines (starting with `•`, `·`, or indented) → Markdown `- ` items
- Returns best-effort Markdown string

**`markdown_to_profile(md_text: str) -> dict`**
- Scans for known section patterns (case-insensitive): `experience`, `work history`, `education`, `skills`, `summary`
- Extracts:
  - **name**: first non-empty line that doesn't look like a heading or contact field
  - **email**: regex on full text
  - **phone**: regex on full text
  - **location**: line near contact info matching city/state pattern
  - **skills**: comma or newline-separated items under skills section
  - **work_history**: patterns like `Title at Company (date–date)` or `Company | Title | dates` — each match produces `{title, company, start, end, summary}`
  - **education**: patterns like `Degree in Field, Institution (year)` — each match produces `{institution, degree, field, graduated, gpa}`
- `target_roles` and `target_salary_min/max` are **not extracted** — left as defaults, not shown in the UI
- Parsing is best-effort; the editable form is the correction mechanism

### New dependency: `pdfplumber`

Add to `requirements.txt`.

### New endpoints in `web/routers/config.py`

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/config/profiles` | Returns list of all profiles `[{id, name}]` and `active_id` |
| `POST` | `/api/config/profiles` | Creates a new blank profile with a given `name`; returns `{id, name, data}` |
| `GET` | `/api/config/profiles/{id}` | Returns full profile data for a given profile ID |
| `PUT` | `/api/config/profiles/{id}` | Saves full profile JSON for a given profile ID (upsert) |
| `DELETE` | `/api/config/profiles/{id}` | Deletes a profile |
| `PUT` | `/api/config/profiles/active` | Sets `active_profile_id` in Config table |
| `POST` | `/api/config/profile/parse` | File upload (`.pdf` or `.md`); runs pipeline; returns parsed JSON; does not save |

The parse endpoint receives a multipart file upload, detects type by extension, chains `pdf_to_markdown` + `markdown_to_profile` for PDFs, or just `markdown_to_profile` for `.md`.

## Frontend (`web/static/config.html`)

Remove `config-section--disabled` and the "coming soon" placeholder from the User Profile `<details>` block.

### Layout (top to bottom)

**Profile selector (like LLM provider rows)**
- One row per profile: radio button (selects active) | profile name label | remove button (✕)
- Selecting a radio loads that profile's data into the edit form below
- "+ Add User" button — prompts for a profile name (inline text input + confirm), creates a blank profile via `POST /api/config/profiles`, adds a row, selects it, clears the edit form

**Edit form** (shows data for whichever profile row is selected)

*File upload widget*
- `<input type="file" accept=".pdf,.md">` + "Parse" button (disabled until file selected)
- On parse: POST file to `/api/config/profile/parse`, populate form fields with response

*Flat fields*
- Name, Email, Phone, Location — `<input class="config-input">`
- Skills — single comma-separated `<input class="config-input">`

*Work History* (dynamic rows)
- Each row: Title | Company | Start | End | Summary + remove button (✕)
- "+ Add Work History" button

*Education* (dynamic rows)
- Each row: Institution | Degree | Field | Graduated | GPA + remove button (✕)
- "+ Add Education" button

**Save button** — `PUT /api/config/profiles/{id}` for the currently selected profile, then `PUT /api/config/profiles/active` to persist the active selection
**Save status span** — shows "Saved ✓" or error for 3 seconds

### Page load

`GET /api/config/profiles` → populate the profile selector rows. Load the active profile's data via `GET /api/config/profiles/{active_id}` into the edit form. If no profiles exist, the edit form is empty and disabled until "+ Add User" is clicked.

## Data Shape

### Profile list response (`GET /api/config/profiles`)
```json
{
  "profiles": [{"id": 1, "name": "Software Engineer"}, {"id": 2, "name": "Data Engineer"}],
  "active_id": 1
}
```

### Full profile body (`GET/PUT /api/config/profiles/{id}`)
```json
{
  "id": 1,
  "name": "Software Engineer",
  "data": {
    "email": "matt@example.com",
    "phone": "555-1234",
    "location": "Remote",
    "skills": ["Python", "SQL", "FastAPI"],
    "work_history": [
      {"title": "Engineer", "company": "Acme", "start": "2022-01", "end": "2024-01", "summary": "Built things."}
    ],
    "education": [
      {"institution": "Columbia", "degree": "B.S.", "field": "EE", "graduated": "2018", "gpa": 3.5}
    ],
    "target_salary_min": null,
    "target_salary_max": null,
    "target_roles": [],
    "resume_path": ""
  }
}
```

Note: the `name` field of `UserProfile` dataclass maps to `UserProfileModel.name` (the display label), not a field inside `data`.

## Files Changed

| Action | File |
|--------|------|
| Create | `core/profile_parser.py` |
| Create | `tests/core/test_profile_parser.py` |
| Modify | `db/models.py` — add `name` column to `UserProfileModel` |
| Modify | `web/routers/config.py` — add 7 endpoints |
| Modify | `web/static/config.html` — enable section, add profile selector + edit form |
| Modify | `requirements.txt` — add `pdfplumber` |
