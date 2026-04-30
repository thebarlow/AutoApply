# Architecture

## Top-Level Structure

```
auto_apply/
├── browser-extension/          # Stage 1a: Firefox/Chrome MV3 extension (LinkedIn + Indeed)
│   └── CONTEXT.md
├── scraper/                    # Stage 1b: API scrapers (Remotive, RemoteOK)
├── 3_applicator/               # Stage 3: submit applications (TBD)
│   └── CONTEXT.md
├── core/                       # Shared Python types (JobState, SearchConfig, UserProfile)
├── db/                         # SQLAlchemy models, engine setup, default config seeding
├── scripts/                    # One-time setup scripts (init_db.py)
├── tests/                      # pytest test suite
├── jobs/                       # Shared data (all stages read/write here)
│   ├── pending/                # Staged job JSON awaiting generation
│   ├── processed/              # Archived after generation
│   └── outputs/                # Generated resume/cover letter artifacts
├── CLAUDE.md                   # Project overview + routing rules
└── ARCHITECTURE.md
```

## Data Flow

```
browser-extension                  scraper/ (Remotive, RemoteOK)
        │  POST /api/scraper/stage-job     │  run_scraper()
        └──────────────┬────────────────────┘
                       ▼
              SQLite DB (state=scraped)
                       │  read by
                       ▼
  generate-resume skill (~/.claude/skills/generate-resume/)
                       │  calls Claude API, pandoc
                       ▼
  jobs/outputs/{key}_resume.md
  jobs/outputs/{key}_resume.pdf
  jobs/outputs/{key}_cover.md
                       │  job JSON moved to
                       ▼
  jobs/processed/{key}.json
```

## Module Responsibilities

| Module | Responsibility |
|---|---|
| `browser-extension/` | MV3 extension; injects Scrape buttons on LinkedIn and Indeed; deduplicates; POSTs job data to FastAPI |
| `scraper/` | API scrapers for Remotive and RemoteOK; reads search config from DB; saves scraped jobs to DB |
| `~/.claude/skills/generate-resume/` | Reads pending jobs; prompts Claude for tailored resume and cover letter; renders PDF via Pandoc; archives job JSON |
| `core/types.py` | Shared Python types: `JobState` enum, `SearchConfig` dataclass, `UserProfile` dataclass |
| `db/` | SQLAlchemy ORM models (`Job`, `Config`, `UserProfileModel`), engine setup, default config seeding |
| `scripts/init_db.py` | One-time setup: creates tables and seeds default config |
| `3_applicator/` | Application submission — scope TBD |
