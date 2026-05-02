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
├── web/                        # FastAPI app + Alpine.js dashboard (landing page + API)
│   └── CONTEXT.md
├── 3_applicator/               # Stage 3: submit applications (TBD)
│   └── CONTEXT.md
├── scripts/                    # One-time admin scripts (e.g. state migration)
├── tests/                      # pytest test suite
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
      Score      Resume/Cover
          │            │
          ▼            ▼
    score fields   generator/outputs/{key}_resume.pdf
    updated in DB  generator/outputs/{key}_cover.pdf
                   job.resume_path / cover_path set in DB
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
| `web/` | FastAPI app serving the dashboard UI and REST API; all user-facing job management happens here |
| `3_applicator/` | Application submission — scope TBD |
