# Architecture

## Top-Level Structure

```
auto_apply/
├── 1_scraper/                  # Stage 1: collect job postings
│   ├── indeed-jobs-extension/  # Firefox/Chrome MV3 extension
│   ├── config.json             # Search keywords, sources, filters
│   └── CONTEXT.md
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
Browser Extension (1_scraper)
        │  POST job JSON
        ▼
  n8n Webhook (local)
        │  writes
        ▼
  jobs/pending/*.json
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
| `1_scraper/indeed-jobs-extension/` | Scrapes Indeed saved jobs page; extracts job descriptions; deduplicates; POSTs to n8n |
| n8n (local, not in repo) | Receives webhook payloads from extension and remote job board APIs; writes JSON to `jobs/pending/` |
| `~/.claude/skills/generate-resume/` | Reads pending jobs; prompts Claude for tailored resume and cover letter; renders PDF via Pandoc; archives job JSON |
| `core/types.py` | Shared Python types: `JobState` enum, `SearchConfig` dataclass, `UserProfile` dataclass |
| `db/` | SQLAlchemy ORM models (`Job`, `Config`, `UserProfileModel`), engine setup, default config seeding |
| `scripts/init_db.py` | One-time setup: creates tables and seeds default config |
| `3_applicator/` | Application submission — scope TBD |
