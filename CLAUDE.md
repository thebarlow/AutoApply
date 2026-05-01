# CLAUDE.md

## Project Overview

Automated job application pipeline with three stages:

1. **Scrape** — collect job postings from LinkedIn and Indeed (browser extension) and remote job boards (Remotive, RemoteOK API scrapers), saved to SQLite DB (`state=scraped`)
2. **Generate** — produce tailored resume + cover letter per job using Claude, render to PDF via pandoc/xelatex. Pipeline lives in `generator/generator.py`; artifacts written to `generator/outputs/`.
3. **Apply** — submit applications (scope TBD)

## Routing Rules


| Task | Location | When to go there |
|---|---|---|
| Browser extension (LinkedIn, Indeed) | `browser-extension/` | Modifying extension behavior, selectors, or staging logic |
| API scrapers (Remotive, RemoteOK), scraper config, runner | `scraper/` | Modifying automated API-based job collection |
| Resume/cover letter generation, Claude prompts, PDF rendering, LaTeX templates | `generator/` | Modifying generation pipeline or PDF layout |
| Job application submission, ATS automation, application tracking | `3_applicator/` | Building or modifying the submission pipeline |

## Working in Subdirectories

- Before working in any subdirectory, read its `CONTEXT.md` if one exists.
- Known bugs, limitations, and future improvements belong in the relevant subdirectory's `CONTEXT.md`, not in code comments or this file. Create one if it doesn't exist.

## Formatting Rules

- Prefix confidence in responses with 🟢/🟠/🔴 as per global CLAUDE.md
