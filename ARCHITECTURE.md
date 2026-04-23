# Architecture

## Top-Level Structure

```
auto_apply/
├── 1_scraper/                  # Stage 1: collect job postings
│   ├── indeed-jobs-extension/  # Firefox/Chrome MV3 extension
│   ├── config.json             # Search keywords, sources, filters
│   └── CONTEXT.md
├── 2_generator/                # Stage 2: generate resume + cover letter
│   ├── resume_agent.py         # Main pipeline script
│   ├── resume_template.tex     # XeLaTeX template for Pandoc PDF rendering
│   └── CONTEXT.md
├── 3_applicator/               # Stage 3: submit applications (TBD)
│   └── CONTEXT.md
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
  resume_agent.py (2_generator)
        │  calls claude CLI, pandoc
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
| `2_generator/resume_agent.py` | Reads pending jobs; prompts Claude for tailored resume and cover letter; renders PDF; archives job |
| `2_generator/resume_template.tex` | XeLaTeX template consumed by Pandoc for PDF rendering |
| `3_applicator/` | Application submission — scope TBD |
