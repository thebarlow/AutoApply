# Architecture

## Top-Level Structure

```
auto_apply/
├── browser-extension/          # Stage 1a: Firefox/Chrome MV3 extension (LinkedIn + Indeed)
│   └── CONTEXT.md
├── scraper/                    # Stage 1b: API scrapers (Remotive, RemoteOK)
├── 3_applicator/               # Stage 3: submit applications (TBD)
│   └── CONTEXT.md
├── core/                       # Shared types (JobState, SearchConfig, UserProfile) and scorer
├── db/                         # SQLAlchemy models, engine setup, config seeding, init/seed scripts
├── generator/                  # Resume/cover letter generation; LaTeX templates and output artifacts live here
│   └── outputs/                # Generated resume/cover letter artifacts (gitignored)
├── tests/                      # pytest test suite
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
  generator/outputs/{key}_resume.md
  generator/outputs/{key}_resume.pdf
  generator/outputs/{key}_cover.md
```

## Module Responsibilities

| Module | Responsibility |
|---|---|
| `browser-extension/` | MV3 extension; injects Scrape buttons on LinkedIn and Indeed; deduplicates; POSTs job data to FastAPI |
| `scraper/` | API scrapers for Remotive and RemoteOK; reads search config from DB; saves scraped jobs to DB |
| `~/.claude/skills/generate-resume/` | Reads pending jobs; prompts Claude for tailored resume and cover letter; renders PDF via Pandoc; archives job JSON |
| `core/types.py` | Shared Python types: `JobState` enum, `SearchConfig` dataclass, `UserProfile` dataclass |
| `core/scorer.py` | Scores SCRAPED jobs via Claude; computes desirability/fit scores; transitions job state |
| `db/` | SQLAlchemy ORM models (`Job`, `Config`, `UserProfileModel`), engine setup, default config seeding; `init_db.py` creates tables, `seed_profile.py` loads profile JSON |
| `3_applicator/` | Application submission — scope TBD |
