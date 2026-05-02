# User Profile Config Section — Design Spec

**Date:** 2026-05-02
**Branch:** make-config

## Goal

Implement the User Profile section of the config page. Allows uploading a PDF or Markdown resume, parsing it into structured fields, editing the result, and saving to the database.

## Pipeline

```
PDF → Markdown → JSON → Database
```

For `.md` uploads, the PDF→Markdown stage is skipped.

## Architecture

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
| `POST` | `/api/config/profile/parse` | File upload (`.pdf` or `.md`); runs pipeline; returns JSON; does not save |
| `GET` | `/api/config/profile` | Returns current `UserProfileModel` row as JSON, or empty defaults |
| `PUT` | `/api/config/profile` | Saves full profile JSON to `UserProfileModel` (upsert) |

The parse endpoint receives a multipart file upload, detects type by extension, chains `pdf_to_markdown` + `markdown_to_profile` for PDFs, or just `markdown_to_profile` for `.md`.

## Frontend (`web/static/config.html`)

Remove `config-section--disabled` and the "coming soon" placeholder from the User Profile `<details>` block.

### Layout (top to bottom)

**File upload widget**
- `<input type="file" accept=".pdf,.md">` + "Parse" button (disabled until file selected)
- On click: POST file to `/api/config/profile/parse`, populate form with response

**Flat fields**
- Name, Email, Phone, Location — `<input class="config-input">`
- Skills — single comma-separated `<input class="config-input">`

**Work History** (dynamic rows, like LLM providers)
- Each row: Title | Company | Start | End | Summary (text inputs) + remove button (✕)
- "+ Add Work History" button

**Education** (dynamic rows)
- Each row: Institution | Degree | Field | Graduated | GPA + remove button (✕)
- "+ Add Education" button

**Save button** — `PUT /api/config/profile` with full form state as JSON
**Save status span** — shows "Saved ✓" or error for 3 seconds

### Page load

`GET /api/config/profile` populates all fields on init. Empty defaults if no profile exists yet.

## Data Shape

Matches the existing `UserProfile` dataclass in `core/types.py`. The PUT body:

```json
{
  "name": "Matt Barlow",
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
```

## Files Changed

| Action | File |
|--------|------|
| Create | `core/profile_parser.py` |
| Create | `tests/core/test_profile_parser.py` |
| Modify | `web/routers/config.py` — add 3 endpoints |
| Modify | `web/static/config.html` — enable section, add form |
| Modify | `requirements.txt` — add `pdfplumber` |
