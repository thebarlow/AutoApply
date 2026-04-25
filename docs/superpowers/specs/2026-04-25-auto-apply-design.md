# Auto Apply — System Design

**Date:** 2026-04-25
**Status:** Approved

---

## Goal

Automate job applications end-to-end with minimal human effort. The user triggers a scrape, reviews borderline jobs in a web UI, and the system handles scoring, document generation, form filling, and application tracking. Not required to be 100% automated — human review is acceptable for edge cases.

**Intended use:** Personal tool, shareable with friends/family, portfolio piece.

---

## Pipeline Overview

Five sequential stages, each a discrete Python module:

```
1. Scrape     → pulls jobs from Indeed, Remotive, LinkedIn
2. Score      → rates each job on desirability + fit, auto-approves/rejects by threshold
3. Review     → human approves/rejects borderline jobs via web UI
4. Generate   → produces tailored resume + cover letter per approved job
5. Apply      → fills and submits application form, logs to Google Sheets
```

### Job State Machine

```
scraped → scored → pending_review → approved → generated → applied
                                 → rejected  (terminal)
                                 → failed    (retryable error state)
```

Auto-approve and auto-reject thresholds bypass the review queue. Everything in between goes to human review.

---

## Technology Stack

| Concern | Choice |
|---|---|
| Language | Python |
| Web framework | FastAPI |
| Database | SQLite (local file, no server) |
| Browser automation | Playwright (headed) + playwright-stealth |
| AI | Claude API (Anthropic SDK) |
| PDF rendering | Pandoc + XeLaTeX (existing) |
| Tracking | Google Sheets (via Sheets API) |
| Frontend | Plain HTML/JS (no framework) |

---

## Module Responsibilities

### 1. Scraper (`scraper/`)

Abstract base class `JobSource` with three concrete implementations:

- `IndeedSource` — Playwright, headed, playwright-stealth
- `LinkedInSource` — Playwright, headed, playwright-stealth
- `RemotiveSource` — public REST API, no browser needed

All sources accept a `SearchConfig` (loaded from SQLite) and return `list[Job]`.

**SearchConfig fields:**
- Keywords whitelist / blacklist
- Location preferences
- Remote / hybrid / on-site preference
- Full-time only flag
- Benefits priorities

**Deduplication:** jobs are keyed by URL. Re-scraping never creates duplicates.

Scrape is triggered manually via the web UI "Run Scrape" button. Results are written directly to SQLite in `scraped` state.

The existing browser extension + n8n workflow is superseded by this module and can be deprecated once stable.

### 2. Scorer (`scorer/`)

Claude scores each scraped job on two independent dimensions:

**Desirability score (0–1):** how much the user wants the job
- Salary vs. target
- Benefits alignment
- Remote/location fit
- Full-time vs. contract
- Keyword match (title, company, description)

**Fit score (0–1):** how well the user matches what the job requires
- Required skills vs. user skills
- Years of experience requested
- Education requirements
- Seniority level match

**Final priority score:** `final = w1 * desirability + w2 * fit`

Weights `w1`, `w2`, auto-reject threshold, and auto-approve threshold are configurable via the web UI config panel. Claude suggests starting weights on first run.

Claude returns both scores with a brief natural-language justification for each. User's resume and preferences are injected as prompt context.

State transitions:
- `final < auto_reject_threshold` → `rejected`
- `final > auto_approve_threshold` → `approved`
- otherwise → `pending_review`

### 3. Review Queue (web UI)

Jobs in `pending_review` state are displayed as cards in the web UI, sorted by final score descending.

Each card shows: title, company, location, salary, desirability score, fit score, final score, Claude's justification.

**Approve** → transitions to `approved`, queues for generation.
**Reject** → transitions to `rejected`.

One click per job. No per-field review.

### 4. Generator (`generator/`)

Wraps the existing `~/.claude/skills/generate-resume/` pipeline.

Changes from current implementation:
- Reads approved jobs from SQLite (not `jobs/pending/`)
- Writes artifact paths back to the job record in SQLite
- Transitions job state `approved` → `generated`

Artifacts produced (unchanged):
- `jobs/outputs/{job_key}_resume.md`
- `jobs/outputs/{job_key}_resume.pdf`
- `jobs/outputs/{job_key}_cover.md`

Generation runs automatically when a job is approved. No manual trigger.

### 5. Applicator (`applicator/`)

Uses Playwright (headed) to navigate to the job's application URL and fill the form.

Abstract base class `ATSHandler` with concrete implementations per platform:
- `GreenhouseHandler`
- `LeverHandler`
- `WorkdayHandler`
- `GenericHandler` (fallback for unknown platforms)

**Field handling:**
- Standard fields (name, email, resume upload, work history, education) → filled automatically from user profile stored in SQLite
- Open-ended fields ("Why do you want to work here?") → Claude generates a response using job description + user profile as context
- Unresolvable fields → job flagged, placed in human review queue with Claude's suggested answer pre-filled; user reviews, edits if needed, clicks approve to resume submission

On successful submission:
- Job transitions to `applied`
- Row written to Google Sheets: title, company, salary, location, date applied, application status, desirability score, fit score, final score

---

## Web UI

Local FastAPI app, served at `localhost:8000`. Plain HTML/JS frontend.

**Pages:**
- **Dashboard** — job counts per state, recent activity, "Run Scrape" button
- **Review Queue** — pending_review jobs as cards, approve/reject actions
- **Application Review** — flagged applications with pre-filled suggested answers, approve to submit
- **Config Panel** — two sections:
  - *Search preferences:* keywords, location, salary target, remote preference, job type, benefits priorities
  - *Scoring weights:* sliders for w1/w2, auto-reject threshold, auto-approve threshold

---

## Database Schema (SQLite)

**`jobs`**
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| job_key | TEXT UNIQUE | source + external ID |
| source | TEXT | indeed / remotive / linkedin |
| title | TEXT | |
| company | TEXT | |
| location | TEXT | |
| salary | TEXT | raw string from source |
| remote | BOOLEAN | |
| description | TEXT | |
| url | TEXT UNIQUE | |
| posted_at | TEXT | |
| scraped_at | TEXT | |
| state | TEXT | state machine value |
| desirability_score | REAL | |
| fit_score | REAL | |
| final_score | REAL | |
| score_justification | TEXT | Claude's explanation |
| resume_path | TEXT | |
| cover_path | TEXT | |
| applied_at | TEXT | |
| sheets_row_id | TEXT | for future updates |

**`config`**
Key-value table for all user preferences and scoring weights.

**`user_profile`**
Structured profile: skills, work history, education, target salary, preferences. Used as context in scoring and application prompts.

---

## Project Directory Structure

```
auto_apply/
├── scraper/
│   ├── base.py           # JobSource ABC
│   ├── indeed.py
│   ├── remotive.py
│   └── linkedin.py
├── scorer/
│   └── scorer.py         # Claude-based scoring
├── generator/
│   └── generator.py      # Wraps generate-resume skill
├── applicator/
│   ├── base.py           # ATSHandler ABC
│   ├── greenhouse.py
│   ├── lever.py
│   ├── workday.py
│   └── generic.py
├── web/
│   ├── main.py           # FastAPI app
│   ├── routes/
│   └── static/           # HTML/JS/CSS
├── db/
│   ├── models.py         # SQLAlchemy models
│   └── migrations/
├── sheets/
│   └── sync.py           # Google Sheets integration
├── jobs/                 # Artifact outputs (existing)
│   ├── pending/
│   ├── processed/
│   └── outputs/
├── 1_scraper/            # Existing browser extension (deprecated once scraper/ stable)
├── 3_applicator/         # Superseded by applicator/
├── CLAUDE.md
└── ARCHITECTURE.md
```

---

## Out of Scope

- Scheduled/automatic scraping (manual trigger only)
- Multi-user support
- Cloud deployment
- Email/calendar integration (follow-ups, interview scheduling)
