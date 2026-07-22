# CLAUDE.md

## Project Overview

Automated job application pipeline with three stages:

1. **Scrape** — collect job postings from LinkedIn and Indeed (browser extension) and remote job boards (Remotive, RemoteOK API scrapers), saved to SQLite DB (`state=new`)
2. **Review & Generate** — manage jobs via the React dashboard (`react-dashboard/`); score jobs and generate a tailored résumé + cover letter per job. Generation produces a typed document stored in the `documents` table (the **source of truth**); the `.md` is derived from it and rendered to PDF via pandoc → Jinja2 HTML/CSS templates → Chromium. Users refine (evaluate→patch loop) or edit fields directly, then mark as applied.
3. **Apply** — submit applications (scope TBD)

LLM I/O is structured and DB-backed: responses validate against Pydantic schemas (`core/schemas.py`), prompt templates live in the DB (seeded from `prompts/defaults/`), and generated documents are stored as typed JSON. See `docs/ARCHITECTURE.md` → "LLM & Document Hardening" for the phase breakdown.

## Routing Rules

Read the target directory's `CONTEXT.md` before making changes there.

| Task | Location | Notes |
|---|---|---|
| Browser extension (LinkedIn, Indeed scraping) | `browser-extension/` | Has `CONTEXT.md` with selector docs and known issues |
| API scrapers (Remotive, RemoteOK) | `scraper/` | Has `CONTEXT.md`; active via the "Find Jobs" tab — `POST /api/scraper/search` (preview) + `POST /api/scraper/scrape-selected` (persist + pipeline); the old dormant `POST /api/scraper/run` was retired |
| React dashboard UI, components, layout | `react-dashboard/src/` | `CONTEXT.md` at `react-dashboard/` has the per-file routing table |
| REST API endpoints (all routes) | `web/routers/` | Has `CONTEXT.md` (at `web/`); score/generate logic delegated to `core/job.py`; `routers/scraper.py` has `stage-job` (manual/extension intake), `search`/`last-search` (Find Jobs preview), and `scrape-selected` (Find Jobs persist + pipeline) |
| Job entity methods (score, generate/refine/eval resume+cover, extract) | `core/job.py` | Read `core/CONTEXT.md` first; all LLM-driven logic lives here |
| Shared types, enums, dataclasses | `core/job.py`, `core/user.py` | Read `core/CONTEXT.md` first |
| LLM client construction, model resolution | `core/llm.py` | Read `core/CONTEXT.md` first |
| Logging setup / error logging (rotating file, tracebacks) | `core/logging_config.py` | `setup_logging()` wired at `web`/`tray_app` startup; env vars `LOG_LEVEL`/`LOG_DIR`/`LOG_FILE`; failure paths use `logger.exception` |
| Pydantic schemas (LLM response + stored document models) | `core/schemas.py` | `parse_llm_json`; `ResumeGeneration`, `ResumeDocument`/`CoverDocument` |
| Build/assemble structured documents (snapshot, patch, render to MD) | `core/document_builder.py`, `core/document_assembler.py` | Read `core/CONTEXT.md` first |
| Reconstruct a structured document from rendered Markdown (inverse of assembler) | `core/document_parser.py` | Read `core/CONTEXT.md` first; tolerates legacy LLM markdown; used to backfill missing `documents` rows |
| Interactive document modal + section/item editing & feedback | `react-dashboard/src/components/widgets/DocumentModal.jsx` + `react-dashboard/src/components/widgets/document/` | Read `react-dashboard/CONTEXT.md`; pencil (✎) button on Resume/Cover toolbar; feedback → `POST /{doc_type}/feedback` → `run_user_feedback_refine` in `web/intake_pipeline.py` |
| Skill normalization, case-folded grouping, alias map, frequency aggregation | `core/skill_analytics.py` | No-LLM; alias-aware (`aliases` param, falls back to built-in `_ALIASES`); seeds the `skill_aliases` table. API surface in `web/routers/skills.py` (alias groups, profile skills, ownership) |
| Field-mapping engine (map profile+docs → ATS form fields → `ApplicationPlan`) | `core/application_fields.py`, `core/application_classify.py`, `core/ats_schemas.py`, `core/application_mapper.py` | Read `core/CONTEXT.md` → "Field-mapping engine"; pure/LLM-free engine (essay drafting injected); EEO fields never LLM-inferred; endpoints in `web/routers/scraper.py` (`application-plan` POST/GET) + `web/application_plan_service.py`; `map_fields` metered only on essay pass |
| HTML/CSS PDF templates (Jinja2 + pandoc → Chromium) | `generator/` | Has `CONTEXT.md`; outputs go to `generator/outputs/` |
| LLM prompt templates (scoring, resume, cover, extraction, resume_parse) | `prompts/` | DB-backed; `prompts/defaults/` is seed-only. Has `CONTEXT.md` |
| Database models, session setup, migrations | `db/` | Has `CONTEXT.md`; SQLite via SQLAlchemy; `jobs`/`config`/`profile_config`/`prompts`/`prompt_defaults`/`documents`/`skill_aliases` tables; run `init_db.py` for idempotent migrations. `config` is **global** infra only (seam pointer, migration gates, platform LLM); per-tenant settings (scoring weights, contact links, template paths, scraper prefs) live in `profile_config` — see `web/CONTEXT.md` |
| System tray app (PyQt6) — floating job-card panel, WS client, PDF drag handles | `tray_app/` | Has `CONTEXT.md`; entry point is `tray_app/main.py` |
| Project user docs, developer notes, Excalidraw diagrams | `Obsidian/Auto Apply/` | Has `CONTEXT.md`; served via `web/routers/docs_router.py`; includes untracked `_templates/` |
| Playwright E2E smoke + live-drive harness | `e2e/` | Has `README.md` (usage) + `CONTEXT.md` (caveats); auto-boots/reuses local stack; logs in via the dev-login endpoint below. Not a per-change regression suite. Separate `e2e/extension/` subproject loads the unpacked browser extension via persistent Chromium context (MV3 service worker, headed only) — see `e2e/extension/CONTEXT.md`; run via `cd e2e/extension && npm test` |
| Dev-only endpoints (resume-compare, `POST /api/dev/login` for local E2E, `POST /api/dev/seed-ats-job` for the extension ATS harness) | `web/routers/dev.py` | Read `web/CONTEXT.md` → "Dev Endpoints"; dev-login is non-production only (404s in prod), sets the session the identity gate (`/api/me`) needs. Resolves the login account by `E2E_LOGIN_EMAIL` (default owner) → admin → first, and on an empty DB provisions a throwaway account/profile to drive new-user onboarding. `seed-ats-job` (same prod guard) upserts a staged `Job` for ATS-autofill testing — note it sets the literal string `state="scraped"`, which has no matching `JobState` enum member |
| Backlog, planned work, multi-session task tracking | `.claude/TODO.md` | Update whenever scope changes or an item is completed |

## Running the App

```bat
start.bat        :: server + Stripe webhook listener + tray app
start.bat dev    :: also runs the Vite dev server (cd react-dashboard && npm run dev)
```

Starts the FastAPI server (uvicorn, port 8080) and a `stripe listen` webhook-forwarding window in separate consoles, then launches the PyQt6 tray app in the foreground. Pass `dev` to additionally run the hot-reload frontend dev server.

## Deployment & SaaS Roadmap

The app is **deployed and live** at `https://autoapply.matthewbarlow.me` (Railway: Dockerfile build, managed Postgres, `/data` volume, alembic-on-startup). See `docs/ARCHITECTURE.md` → "Deployment". The hosted instance is gated by **Google/GitHub OAuth** (`web/auth/`); access is invite-gated by `ALLOWED_EMAILS`, with `ADMIN_EMAILS` bypassing the allowlist.

Multi-tenancy is **done** (`profile_id` everywhere via the `current_profile_id` seam + `scoped()` + a `before_flush` tenant guard; the platform owns the LLM key via env). The app is being converted to a multi-user SaaS in four sequenced sub-projects — **Auth → Credits → Payments → Onboarding** — each with its own spec → plan → impl cycle. **Sub-project 1 (Auth & Identity) is DONE and live**: Authlib Google/GitHub OAuth + Starlette signed-cookie sessions; `account`/`identity` tables (1 account = 1 `user_profile`, linked by verified email); the seam resolves the logged-in account's profile in production; a pure-ASGI gate (`web/auth/middleware.py`) replaced the old HTTP Basic gate. Read `web/CONTEXT.md` → "Auth" before touching auth. **Sub-projects 2 (Credits & Metering) and 3 (Payments) are DONE and live**; **sub-project 4 (Onboarding) is in progress** — the first-run flow is now a single resume-upload modal (no user API-key step; platform owns the LLM key), with credits/buy-flow surfacing and the job-ingestion gap still open. Full roadmap, status, and design pointers live in `.claude/TODO.md` → "Hosting / SaaS conversion". When working on hosted/multi-user/auth/credits/payments features, read `.claude/TODO.md` and the relevant `docs/superpowers/specs|plans/*` first.

## Working in Subdirectories

- Before working in any subdirectory, read its `CONTEXT.md` if one exists.
- Known bugs, limitations, and future improvements belong in the relevant subdirectory's `CONTEXT.md`, not in code comments or this file. Create one if it doesn't exist.
- **Data backups** (SQLite DB dumps, live-profile JSON snapshots, or any pre-write safety copy) go in `backups/` at the project root. The folder is tracked (via `.gitkeep`) but its contents are gitignored. Never scatter `*.bak*` files in the project root or subdirectories.
- Update `docs/ARCHITECTURE.md` when shipping a release, not per commit — do it automatically as part of the release.

## Formatting Rules

- Prefix confidence in responses with 🟢/🟠/🔴 as per global CLAUDE.md
