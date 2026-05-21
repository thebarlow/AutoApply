# Architecture

## Top-Level Structure

```
auto_apply/
├── browser-extension/          # Stage 1a: Firefox/Chrome MV3 extension (LinkedIn + Indeed)
│   └── CONTEXT.md
├── scraper/                    # Stage 1b: API scrapers (Remotive, RemoteOK)
├── core/                       # Shared types (JobState, SearchConfig, UserProfile) and scorer
├── db/                         # SQLAlchemy models, engine setup, config seeding, init/seed scripts
├── generator/                  # Resume/cover letter generation; LaTeX templates and output artifacts live here
│   └── outputs/                # Generated resume/cover letter artifacts (gitignored)
├── react-dashboard/            # React frontend dashboard (Vite + React)
│   └── src/
├── web/                        # FastAPI app + REST API (no longer serves frontend UI)
│   └── CONTEXT.md
├── 3_applicator/               # Stage 3: submit applications (TBD)
│   └── CONTEXT.md
├── tray_app/                   # Stage 3: PyQt6 system tray app for drag-and-drop application submission
├── scripts/                    # One-time admin scripts (e.g. state migration)
├── tests/                      # pytest test suite
├── start.bat                   # Launch script: starts uvicorn server + tray app together
├── CLAUDE.md                   # Project overview + routing rules
└── ARCHITECTURE.md
```

## Job State Machine

Jobs move through four states:

| State | Meaning | How entered |
|---|---|---|
| `pending` | Default — scraped, awaiting action | Set on ingest by scraper/extension |
| `applied` | Application submitted | User clicks "Mark as Applied" in dashboard |
| `rejected` | Application rejected by employer | Future: set by applicator or manually |
| `failed` | Technical failure during processing | Set by generator on error |

Scoring (`core/scorer.py`) updates score fields but does **not** change state. Jobs remain `pending` after scoring.

## Data Flow

```
browser-extension                  scraper/ (Remotive, RemoteOK)
        │  POST /api/scraper/stage-job     │  run_scraper()
        └──────────────┬────────────────────┘
                       ▼
              SQLite DB (state=pending)
                       │
                       ▼
              web/ dashboard
          ┌────────────┼────────────┐
          │            │            │
    Calculate     Generate     Mark Applied
      Score      Resume/Cover       │
          │            │            ▼
          ▼            ▼      Apply Button
    score fields   generator/outputs/{key}_resume.pdf
    updated in DB  generator/outputs/{key}_cover.pdf
                   job.resume_path / cover_path set in DB
                                         │
                                POST /api/jobs/{key}/apply
                                         │
                                  WebSocket → tray_app
                                         │
                            User drags files to ATS
                                         │
                        POST /api/jobs/{key}/confirm-applied
                                         │
                                  state=applied
```

## Module Responsibilities

| Module | Responsibility |
|---|---|
| `browser-extension/` | MV3 extension; injects Scrape buttons on LinkedIn and Indeed; deduplicates; POSTs job data to FastAPI |
| `scraper/` | API scrapers for Remotive and RemoteOK; reads search config from DB; saves scraped jobs to DB |
| `core/types.py` | Shared Python types: `JobState` enum (4 states), `SearchConfig` dataclass, `UserProfile` dataclass |
| `core/scorer.py` | Scores jobs via Claude; computes desirability/fit/final scores; does not change job state |
| `db/` | SQLAlchemy ORM models (`Job`, `Config`, `UserProfileModel`), engine setup, default config seeding; `init_db.py` creates tables, `seed_profile.py` loads profile JSON |
| `generator/generator.py` | Generates tailored resume and cover letter via Claude; renders PDF via pandoc/xelatex; updates `resume_path`/`cover_path` on the job |
| `react-dashboard/` | React + Vite frontend; job table, overlays, action buttons, settings — communicates with FastAPI via REST API |
| `web/` | FastAPI app serving the REST API; all backend job management logic and endpoints live here |
| `3_applicator/` | Application submission — scope TBD |
| `tray_app/` | Standalone PyQt6 desktop process; receives job payloads from FastAPI over WebSocket; presents draggable resume/cover letter handles; marks jobs applied on checkmark |
