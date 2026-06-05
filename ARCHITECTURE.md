# Architecture

## Top-Level Structure

```
auto_apply/
├── browser-extension/          # Stage 1a: Firefox/Chrome MV3 extension (LinkedIn + Indeed)
│   └── CONTEXT.md
├── scraper/                    # Stage 1b: API scrapers (Remotive, RemoteOK) — dormant
│   └── CONTEXT.md
├── core/                       # Shared business logic: Job/User entities, LLM client, schemas, document build/assemble
│   └── CONTEXT.md
├── db/                         # SQLAlchemy models, engine setup, config/prompt seeding, idempotent column migrations
│   └── CONTEXT.md
├── prompts/                    # Seed source for DB-backed prompt templates (defaults/*.md); not read at runtime
│   └── CONTEXT.md
├── generator/                  # PDF rendering assets: Jinja2 HTML + CSS templates and generated output artifacts
│   ├── CONTEXT.md
│   └── outputs/                # Generated {key}_resume.md/.pdf, {key}_cover.md/.pdf, turn snapshots (gitignored)
├── react-dashboard/            # React + Vite frontend dashboard
│   └── CONTEXT.md
├── web/                        # FastAPI app + REST API (does not serve frontend HTML)
│   └── CONTEXT.md
├── tray_app/                   # PyQt6 system tray app: floating job cards, WS client, draggable PDF handles
│   └── CONTEXT.md
├── profiles/                   # User profile JSON (seed source for the user_profile table)
├── Obsidian/                   # Project user docs / developer notes (served via docs_router)
├── docs/                       # Specs, plans, and the superpowers workflow assets
├── tests/                      # pytest suite (core/, web/)
├── start.bat                   # Launch script: starts uvicorn server + tray app together
├── CLAUDE.md                   # Project overview + routing rules
└── ARCHITECTURE.md
```

## Pipeline Overview

Three stages: **Scrape → Review & Generate → Apply**.

1. **Scrape** — the browser extension (LinkedIn/Indeed) and dormant API scrapers POST jobs to the API; rows land in SQLite.
2. **Review & Generate** — the React dashboard drives per-job scoring, structured résumé/cover generation, an evaluate→refine quality loop, and structured field-level editing. All LLM-driven logic lives on the `Job` entity in `core/job.py`.
3. **Apply** — generated PDFs are handed to the PyQt6 tray app for drag-and-drop submission to an ATS; the job is then marked applied.

## Job State Machine

`JobState` (in `core/job.py`) has seven values:

| State | Meaning |
|---|---|
| `new` | Freshly ingested, awaiting intake/extraction |
| `pending_review` | Has generated artifacts awaiting user review |
| `ready` | Reviewed and ready to submit |
| `applied` | Application submitted |
| `contact` | Employer/recruiter contact made |
| `rejected` | Rejected by employer |
| `deleted` | Soft-deleted |

Scoring updates score fields but does **not** change state.

## Data Flow

```
browser-extension                  scraper/ (Remotive, RemoteOK — dormant)
        │  POST /api/scraper/stage-job     │  POST /api/scraper/run
        └──────────────┬────────────────────┘
                       ▼
              SQLite DB (jobs, state=new)
                       │  intake → extract_description (LLM → ext_* columns)
                       ▼
                  web/ + React dashboard
          ┌────────────┬───────────────────┬──────────────┐
          │            │                   │              │
        Score      Generate            Evaluate→Refine   Edit fields
       (LLM)    résumé / cover           loop (LLM)      (structured PUT)
          │            │                   │              │
          ▼            ▼                   ▼              ▼
   score fields   documents table  ── single source of truth ──┐
   updated in DB  (structured_json per job_key+doc_type)        │
                       │  derived (never edited directly)       │
                       ▼                                        │
        generator/outputs/{key}_resume.md  ──render──▶ {key}_resume.pdf
        generator/outputs/{key}_cover.md   ──render──▶ {key}_cover.pdf
                       │
              POST /api/jobs/{key}/apply → WebSocket → tray_app
                       │
              user drags PDFs to ATS → mark applied → state=applied
```

PDF rendering: `core/utils.render_pdf` runs **pandoc → Jinja2 HTML template + paired CSS → Chromium** (headless print-to-PDF), with optional single-page auto-shrink. Templates live in `generator/` (`*_template.html` + `*.css`).

## Module Responsibilities

| Module | Responsibility |
|---|---|
| `browser-extension/` | MV3 extension; injects Scrape buttons on LinkedIn/Indeed; dedupes; POSTs job data to the API |
| `scraper/` | API scrapers for Remotive/RemoteOK (dormant; `POST /api/scraper/run` registered but not wired into the UI) |
| `core/job.py` | `Job` entity + **all** LLM-driven methods: score, extract, generate résumé/cover, evaluate, refine; structured-JSON parsing with retry; PDF rendering orchestration |
| `core/user.py` | `User` entity; profile load/save/validation, prompt resolution, degree/skill helpers |
| `core/llm.py` | OpenAI-SDK client construction + model resolution (multi-provider); `call_llm` single-turn helper + session-cost accounting |
| `core/schemas.py` | Pydantic models: LLM **response** contracts (`ScoreResponse`, `EvalResponse`, `ExtractionResponse`, `ParseResponse`, `ResumeGeneration`) and stored **document** models (`ResumeDocument`, `CoverDocument`, sub-models); `parse_llm_json` |
| `core/document_builder.py` | Snapshots profile at generation time + joins LLM prose to structural data (`build_resume_document`/`build_cover_document`); `apply_resume_patch` for refine |
| `core/document_assembler.py` | Pure renderer: structured document → canonical-ordered Markdown (no DB, no LLM) |
| `core/utils.py` | `render_pdf` (pandoc→HTML→Chromium), sanitization, path helpers |
| `core/skill_analytics.py` | Skill token normalization + frequency aggregation across jobs (no LLM) |
| `core/session_cost.py` | Thread-safe per-session LLM spend accumulator |
| `db/` | SQLAlchemy models (`Job`, `Config`, `Prompt`, `PromptDefault`, `Document`, user profile), engine/session setup, config + prompt seeding, idempotent column/prompt migrations |
| `prompts/` | `defaults/*.md` seed source for the DB-backed prompt tables (not read at runtime) |
| `generator/` | Jinja2 HTML + CSS PDF templates and generated output artifacts (`outputs/`) |
| `react-dashboard/` | React + Vite frontend; job table, overlays, structured document editor, settings — talks to the API via REST + SSE |
| `web/` | FastAPI app + REST API; resolves LLM client/prompt/template then delegates to `Job`; document GET/PUT API; evaluate→refine intake pipeline |
| `tray_app/` | PyQt6 desktop process; receives job payloads over WebSocket; draggable résumé/cover handles; marks jobs applied |

## LLM & Document Hardening (Phases 1–3b)

A four-phase initiative moved the pipeline from free-form text toward typed, DB-backed data.

- **Phase 1 — Structured LLM parsing.** LLM responses for data tasks are validated against Pydantic models via `core/schemas.py` `parse_llm_json` (`ScoreResponse`, `EvalResponse`, `ExtractionResponse`, `ParseResponse`). No more ad-hoc string parsing.
- **Phase 2 — Prompts in the DB.** Prompt templates moved out of files into the `prompt_defaults` (factory) and `prompts` (per-profile) tables. `prompts/defaults/*.md` are seed-only; runtime resolution is `User.resolve_prompt` with auto-repair from defaults. Edited via `web/routers/prompts.py`.
- **Phase 3a — Structured document generation.** Generation returns a JSON `ResumeGeneration` contract, is built into a typed `ResumeDocument`/`CoverDocument`, and is stored in the `documents` table (`structured_json`, one row per `job_key`+`doc_type`). The `.md` is **derived** by assembling that document; PDFs render from the `.md`. Render metadata (contact/education) is snapshotted at generation time.
- **Phase 3b — Document as single source of truth.** The `documents` row is authoritative; the `.md`/PDF are purely derived and written only by `write_resume_markdown`/`write_cover_markdown`. Raw-Markdown editing was retired in favor of a structured `GET/PUT /api/jobs/{key}/{doc_type}/document` API and a React per-section form editor. Refine became a prose-only **keyed patch** (`apply_resume_patch`) that never touches structural facts; per-turn refinement snapshots are structured JSON, so restore-best keeps the document, `.md`, and PDF in sync.
- **JSON-output hardening.** Because small/fast models occasionally emit invalid JSON (a markdown value breaking out of its string), the structured résumé generate/refine calls go through `core/job.py` `_llm_json_with_retry`, which appends a strict-JSON instruction and retries once with a corrective nudge on a parse failure.
- **ATS gate + apply hard-block.** `core/ats_gate.py` adds a two-layer ATS parseability check over the rendered résumé PDF: a deterministic mechanical layer (contact order, section presence, required-skill survival, glyph-junk, text-layer) that hard-blocks on any critical issue, and an LLM-powered semantic roundtrip check (advisory). `POST /api/jobs/{key}/confirm-applied` (`web/routers/tray.py`) runs the gate at apply time, returning HTTP 409 on a critical failure and HTTP 422 if artifacts are missing. A DOCX résumé export (via pandoc, résumé-only) is also produced as an alternate artifact and stored as `resume_docx_path` on the job row. The résumé HTML template (`generator/master.css`) received a single-column flex-wrap fix to the header so the contact line renders correctly in both PDF and DOCX export.

## Key Invariants

- `Job` LLM methods receive an already-constructed client + model string; they do not read config themselves.
- DB writes inside `Job` methods use the caller-supplied session; callers own commit/rollback (except `Document.upsert`, which commits).
- The `documents` table is the source of truth; `.md` and PDF are derived artifacts and are never hand-edited.
- Structured résumé generate/refine route through `_llm_json_with_retry`; `_refine_doc_md` uses `max_tokens=32768` to avoid truncation.
