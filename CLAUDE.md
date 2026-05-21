# CLAUDE.md

## Project Overview

Automated job application pipeline with three stages:

1. **Scrape** — collect job postings from LinkedIn and Indeed (browser extension) and remote job boards (Remotive, RemoteOK API scrapers), saved to SQLite DB (`state=pending`)
2. **Review & Generate** — manage jobs via the React dashboard (`react-dashboard/`); score jobs with Claude, generate tailored resume + cover letter per job (rendered to PDF via pandoc/xelatex), mark as applied
3. **Apply** — submit applications (scope TBD)

## Routing Rules

| Task | Location | When to go there |
|---|---|---|
| Browser extension (LinkedIn, Indeed) | `browser-extension/` | Modifying extension behavior, selectors, or staging logic |
| API scrapers (Remotive, RemoteOK), scraper config, runner | `scraper/` | Modifying automated API-based job collection |
| React dashboard UI, job table, overlay, action buttons | `react-dashboard/src/` | Modifying frontend behavior or layout |
| REST API endpoints (score, generate, delete, state) | `web/routers/` | Modifying API behavior or adding new endpoints |
| Resume/cover letter generation, Claude prompts, PDF rendering, LaTeX templates | `generator/` | Modifying generation pipeline or PDF layout |
| Job scoring logic, Claude prompts for scoring | `core/scorer.py` | Modifying scoring behavior or weights |
| Job state machine, shared types | `core/types.py` | Adding/changing job states or shared dataclasses |
| Job application submission, ATS automation, application tracking | `3_applicator/` | Building or modifying the submission pipeline |

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
