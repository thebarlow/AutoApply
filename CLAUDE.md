# CLAUDE.md

## Project Overview

Automated job application pipeline with three stages:

1. **Scrape** — collect job postings from Indeed (browser extension) and remote job boards (n8n), stage as JSON in `jobs/pending/`
2. **Generate** — produce tailored resume + cover letter per job using Claude, render to PDF. Use the `/generate-resume` skill. Templates and pipeline logic live in `~/.claude/skills/generate-resume/`. Pass paths explicitly:
   ```
   python ~/.claude/skills/generate-resume/agent.py --pending jobs/pending --processed jobs/processed --outputs jobs/outputs
   ```
3. **Apply** — submit applications (scope TBD)

## Shared Data Layout

```
jobs/
├── pending/      ← incoming job JSON, awaiting generation
├── processed/    ← job JSON moved here after generation completes
└── outputs/      ← generated artifacts: {job_key}_resume.md, .pdf, _cover.md
```

## Routing Rules


| Task | Location | When to go there |
|---|---|---|
| Browser extension, webhook config, n8n workflow, job scraping logic | `1_scraper/` | Modifying how job data is collected or staged |
| Resume/cover letter generation, LaTeX templates, Claude prompts, PDF rendering | `~/.claude/skills/generate-resume/` | Modifying templates, prompts, or pipeline logic |
| Job application submission, ATS automation, application tracking | `3_applicator/` | Building or modifying the submission pipeline |

## Formatting Rules

- Prefix confidence in responses with 🟢/🟠/🔴 as per global CLAUDE.md
