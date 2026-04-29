# Config Tab Design

**Date:** 2026-04-29
**Branch:** make-config

## Overview

Add a Config page at `/config` where the user can view and edit scraper sources, search settings, and user profile. Single Save button commits all three sections in parallel.

## File Structure

```
web/
├── static/
│   ├── index.html          (existing — update nav active state)
│   ├── config.html         (new)
│   └── style.css           (existing, shared)
└── routers/
    ├── jobs.py             (existing)
    ├── scraper.py          (existing)
    └── config.py           (new)
```

## Routing

Add to `web/main.py`:
- `app.include_router(config.router)`
- `GET /config` → serves `config.html`

Nav links in both `index.html` and `config.html` get an `active` CSS class hardcoded on the current page's link.

## API Endpoints

New router: `web/routers/config.py` with prefix `/api/config`.

### Sources
- `GET /api/config/sources` → `{ "remotive": bool, "remoteok": bool }`
- `PUT /api/config/sources` → same shape; writes to `Config` table key `scraper_sources` as comma-separated string of enabled IDs. Keeps compatibility with existing scraper router.

### Search Settings
- `GET /api/config/search` → `{ "keywords": list[str], "location": str, "remote_only": bool, "full_time_only": bool, "target_salary_min": int | null }`
- `PUT /api/config/search` → same shape; writes to `Config` table as JSON under key `search_config`. Not yet wired to scraper — persisted for future use.

### Profile
- `GET /api/profile` → full profile dict parsed from `UserProfileModel.data`
- `PUT /api/profile` → validates top-level shape, saves JSON. Returns 422 if required keys missing or `work_history` entries use `summary` instead of `bullets`.

Required top-level keys: `name`, `skills`, `work_history`, `education`.
`work_history` entries must have `bullets: list[str]`, not `summary: str`.

## User Profile Schema

The `UserProfile` dataclass in `core/types.py` is updated:
- `WorkHistoryEntry.summary: str` → `WorkHistoryEntry.bullets: list[str]`
- Add `summary: str` to `UserProfile` (professional summary paragraph)
- Add `links: dict[str, str]` to `UserProfile` (e.g. `{"linkedin": "...", "github": "..."}`)
- Add optional `projects: list[ProjectEntry]` to `UserProfile`

New `ProjectEntry` dataclass: `name: str`, `description: str`, `tech: list[str]`, `bullets: list[str]`.

## UI Layout (`config.html`)

Same nav as `index.html` with `Config` link marked active. `main` content area (max-width 860px, same as queue) contains three stacked sections with headings, followed by a single Save button.

### Sources section
Two checkboxes: `remotive`, `remoteok`. Pre-populated from `GET /api/config/sources`.

### Search Settings section
- Keywords — text input (comma-separated, split to list on save)
- Location — text input
- Remote only — checkbox
- Full time only — checkbox
- Min salary — number input (nullable, blank = null)

Pre-populated from `GET /api/config/search`.

### User Profile section
Raw JSON textarea pre-populated from `GET /api/profile`. Small note above documenting expected shape. On 422, display the API error message inline below the textarea.

### Save button
Single button at bottom of page. On click, fires all three PUTs in parallel (`Promise.all`). Shows inline status: "Saved ✓" on full success, or "Error — [message]" listing which section(s) failed.

## CSS

No new CSS needed beyond:
- `.active` nav link style (white text + underline or similar indicator)
- Form layout styles: label/input pairs, section headings, textarea sizing

Reuse existing `.btn`, `.card-success`, `.card-error` patterns for Save button and feedback.
