# CLAUDE.md

## Project Overview

Automated job application pipeline with three stages:

1. **Scrape** — collect job postings from LinkedIn and Indeed (browser extension) and remote job boards (Remotive, RemoteOK API scrapers), saved to SQLite DB (`state=pending`)
2. **Review & Generate** — manage jobs via the React dashboard (`react-dashboard/`); score jobs with Claude, generate tailored resume + cover letter per job (rendered to PDF via pandoc/xelatex), mark as applied
3. **Apply** — submit applications (scope TBD)

## Routing Rules

Read the target directory's `CONTEXT.md` before making changes there.

| Task | Location | Notes |
|---|---|---|
| Browser extension (LinkedIn, Indeed scraping) | `browser-extension/` | Has `CONTEXT.md` with selector docs and known issues |
| API scrapers (Remotive, RemoteOK) — dormant | `scraper/` | Has `CONTEXT.md`; `POST /api/scraper/run` is registered but not called from the React UI (only via raw HTTP, requires `scraper_sources` config) |
| React dashboard UI, components, layout | `react-dashboard/src/` | Has `CONTEXT.md` with per-file routing table |
| REST API endpoints (all routes) | `web/routers/` | Has `CONTEXT.md` (at `web/`); score/generate logic delegated to `core/job.py`; `routers/scraper.py` has `stage-job` (manual/extension intake, used by UI) and `run` (API scrapers, dormant) |
| Job entity methods (score, generate_resume_md/pdf, generate_cover_md/pdf) | `core/job.py` | Read `core/CONTEXT.md` first |
| Shared types, enums, dataclasses | `core/job.py`, `core/user.py` | Read `core/CONTEXT.md` first |
| LLM client construction, model resolution | `core/llm.py` | Read `core/CONTEXT.md` first |
| LaTeX resume/cover letter templates | `generator/` | Has `CONTEXT.md`; outputs go to `generator/outputs/` |
| LLM prompt templates (scoring, resume, cover, extraction, resume_parse) | `prompts/` | Has `CONTEXT.md`; active defaults in `prompts/defaults/` |
| Database models, session setup, migrations | `db/` | Has `CONTEXT.md`; SQLite via SQLAlchemy, run `init_db.py` for idempotent column migrations |
| System tray app (PyQt6) — floating job-card panel, WS client, PDF drag handles | `tray_app/` | Has `CONTEXT.md`; entry point is `tray_app/main.py` |
| Project user docs, developer notes, Excalidraw diagrams | `Obsidian/Auto Apply/` | Has `CONTEXT.md`; served via `web/routers/docs_router.py`; includes untracked `_templates/` |
| Backlog, planned work, multi-session task tracking | `TODO.md` | Update whenever scope changes or an item is completed |

## Running the App

```bat
start.bat
```

Starts the FastAPI server (uvicorn, port 8080) in a separate console window and launches the PyQt6 tray app in the foreground.

## Working in Subdirectories

- Before working in any subdirectory, read its `CONTEXT.md` if one exists.
- Known bugs, limitations, and future improvements belong in the relevant subdirectory's `CONTEXT.md`, not in code comments or this file. Create one if it doesn't exist.

## Formatting Rules

- Prefix confidence in responses with 🟢/🟠/🔴 as per global CLAUDE.md
