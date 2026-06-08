# CLAUDE.md

## Project Overview

Automated job application pipeline with three stages:

1. **Scrape** — collect job postings from LinkedIn and Indeed (browser extension) and remote job boards (Remotive, RemoteOK API scrapers), saved to SQLite DB (`state=new`)
2. **Review & Generate** — manage jobs via the React dashboard (`react-dashboard/`); score jobs and generate a tailored résumé + cover letter per job. Generation produces a typed document stored in the `documents` table (the **source of truth**); the `.md` is derived from it and rendered to PDF via pandoc → Jinja2 HTML/CSS templates → Chromium. Users refine (evaluate→patch loop) or edit fields directly, then mark as applied.
3. **Apply** — submit applications (scope TBD)

LLM I/O is structured and DB-backed: responses validate against Pydantic schemas (`core/schemas.py`), prompt templates live in the DB (seeded from `prompts/defaults/`), and generated documents are stored as typed JSON. See `ARCHITECTURE.md` → "LLM & Document Hardening" for the phase breakdown.

## Routing Rules

Read the target directory's `CONTEXT.md` before making changes there.

| Task | Location | Notes |
|---|---|---|
| Browser extension (LinkedIn, Indeed scraping) | `browser-extension/` | Has `CONTEXT.md` with selector docs and known issues |
| API scrapers (Remotive, RemoteOK) — dormant | `scraper/` | Has `CONTEXT.md`; `POST /api/scraper/run` is registered but not called from the React UI (only via raw HTTP, requires `scraper_sources` config) |
| React dashboard UI, components, layout | `react-dashboard/src/` | `CONTEXT.md` at `react-dashboard/` has the per-file routing table |
| REST API endpoints (all routes) | `web/routers/` | Has `CONTEXT.md` (at `web/`); score/generate logic delegated to `core/job.py`; `routers/scraper.py` has `stage-job` (manual/extension intake, used by UI) and `run` (API scrapers, dormant) |
| Job entity methods (score, generate/refine/eval resume+cover, extract) | `core/job.py` | Read `core/CONTEXT.md` first; all LLM-driven logic lives here |
| Shared types, enums, dataclasses | `core/job.py`, `core/user.py` | Read `core/CONTEXT.md` first |
| LLM client construction, model resolution | `core/llm.py` | Read `core/CONTEXT.md` first |
| Pydantic schemas (LLM response + stored document models) | `core/schemas.py` | `parse_llm_json`; `ResumeGeneration`, `ResumeDocument`/`CoverDocument` |
| Build/assemble structured documents (snapshot, patch, render to MD) | `core/document_builder.py`, `core/document_assembler.py` | Read `core/CONTEXT.md` first |
| Skill normalization, case-folded grouping, alias map, frequency aggregation | `core/skill_analytics.py` | No-LLM; alias-aware (`aliases` param, falls back to built-in `_ALIASES`); seeds the `skill_aliases` table. API surface in `web/routers/skills.py` (alias groups, profile skills, ownership) |
| HTML/CSS PDF templates (Jinja2 + pandoc → Chromium) | `generator/` | Has `CONTEXT.md`; outputs go to `generator/outputs/` |
| LLM prompt templates (scoring, resume, cover, extraction, resume_parse) | `prompts/` | DB-backed; `prompts/defaults/` is seed-only. Has `CONTEXT.md` |
| Database models, session setup, migrations | `db/` | Has `CONTEXT.md`; SQLite via SQLAlchemy; `jobs`/`config`/`prompts`/`prompt_defaults`/`documents`/`skill_aliases` tables; run `init_db.py` for idempotent migrations |
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
