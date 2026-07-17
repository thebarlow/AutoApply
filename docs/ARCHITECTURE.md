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
├── docs/                       # ARCHITECTURE.md (this file), user docs, specs/plans (superpowers)
├── tests/                      # pytest suite (core/, web/)
├── start.bat                   # Launch script: starts uvicorn server + tray app together
├── README.md                   # Human-facing setup + usage guide
└── .claude/                    # CLAUDE.md (routing rules), TODO.md (backlog), skills, settings
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
| `core/document_parser.py` | Inverse of the assembler: reconstructs a structured document from rendered Markdown (canonical + legacy LLM formats); used to backfill missing `documents` rows |
| `core/utils.py` | `render_pdf` (pandoc→HTML→Chromium), sanitization, path helpers |
| `core/skill_analytics.py` | Skill token normalization + frequency aggregation across jobs (no LLM) |
| `core/session_cost.py` | Thread-safe per-session LLM spend accumulator |
| `core/logging_config.py` | `setup_logging()`: configures root logging (stdout + size-rotating file, 5MB×5) and a thread/sys excepthook so background-thread failures are captured with tracebacks; env-configurable, idempotent, called at `web`/`tray_app` startup. Failure paths log via `logger.exception` |
| `db/` | SQLAlchemy models (`Job`, `Config`, `ProfileConfig`, `Prompt`, `PromptDefault`, `Document`, `SkillAlias`, user profile), engine/session setup, config + prompt seeding, idempotent column/prompt migrations. `Config` is a **global** key-value store (infra keys only); `ProfileConfig` is its per-tenant counterpart (composite PK `profile_id`+`key`) holding scoring weights, contact links, template paths, and scraper prefs — a tenant guard blocks unstamped inserts |
| `prompts/` | `defaults/*.md` seed source for the DB-backed prompt tables (not read at runtime) |
| `generator/` | Jinja2 HTML + CSS PDF templates and generated output artifacts (`outputs/`) |
| `react-dashboard/` | React + Vite frontend; job table, overlays, interactive document modal (inline edit + feedback), settings — talks to the API via REST + SSE |
| `web/` | FastAPI app + REST API; resolves LLM client/prompt/template then delegates to `Job`; document GET/PUT API; evaluate→refine intake pipeline |
| `tray_app/` | PyQt6 desktop process; receives job payloads over WebSocket; draggable résumé/cover handles; marks jobs applied |

## LLM & Document Hardening (Phases 1–3b)

A four-phase initiative moved the pipeline from free-form text toward typed, DB-backed data.

- **Phase 1 — Structured LLM parsing.** LLM responses for data tasks are validated against Pydantic models via `core/schemas.py` `parse_llm_json` (`ScoreResponse`, `EvalResponse`, `ExtractionResponse`, `ParseResponse`). No more ad-hoc string parsing.
- **Phase 2 — Prompts in the DB.** Prompt templates moved out of files into the `prompt_defaults` (factory) and `prompts` (per-profile) tables. `prompts/defaults/*.md` are seed-only; runtime resolution is `User.resolve_prompt` with auto-repair from defaults. Edited via `web/routers/prompts.py`.
- **Phase 3a — Structured document generation.** Generation returns a JSON `ResumeGeneration` contract, is built into a typed `ResumeDocument`/`CoverDocument`, and is stored in the `documents` table (`structured_json`, one row per `job_key`+`doc_type`). The `.md` is **derived** by assembling that document; PDFs render from the `.md`. Render metadata (contact/education) is snapshotted at generation time.
- **Phase 3b — Document as single source of truth.** The `documents` row is authoritative; the `.md`/PDF are purely derived and written only by `write_resume_markdown`/`write_cover_markdown`. Raw-Markdown editing was retired in favor of a structured `GET/PUT /api/jobs/{key}/{doc_type}/document` API and a React per-section form editor. Refine became a prose-only **keyed patch** (`apply_resume_patch`) that never touches structural facts; per-turn refinement snapshots are structured JSON, so restore-best keeps the document, `.md`, and PDF in sync.
- **Interactive document modal + user feedback.** The Resume/Cover toolbar's pencil (✎) button opens `DocumentModal` (`react-dashboard/src/components/widgets/document/`), which renders the structured document as interactive HTML: hover-highlight, click-to-edit-inline (`PUT .../document`), and click-to-attach feedback per item or per section. Feedback batches are submitted to `POST .../feedback` → `run_user_feedback_refine`, a one-shot refine (reuses the refine path, eval-for-score, **no** restore-best; résumés trigger the ATS gate). Backfill is **parse-on-read** (`core/document_parser`): `GET .../document` reconstructs a missing row from the on-disk `.md` without persisting; the feedback path persists one first (`_ensure_document_row`) since the refine mutates it.
- **JSON-output hardening.** Because small/fast models occasionally emit invalid JSON (a markdown value breaking out of its string), the structured résumé generate/refine calls go through `core/job.py` `_llm_json_with_retry`, which appends a strict-JSON instruction and retries once with a corrective nudge on a parse failure.
- **Profile Schema Engine (sub-project #1 — tree as source of truth).** `core/profile_tree.py` introduces a recursive, closed-vocabulary node tree (`RootNode → SectionNode → ListNode/GroupNode → FieldNode`) as the authoritative representation of a user profile. `User._hydrate` builds or migrates the tree on every load (`legacy_to_tree` on first load, `RootNode.model_validate` thereafter), validates it via `validate_tree`, and derives all document-section attrs (`work_history`/`education`/`projects`/`skills`/contact/`hero`) from it via `tree_to_legacy`. The tree is persisted in `user_profile.data` as `"profile_tree"`. Metadata (target roles/salary, resume/md paths) stays as flat keys in `data`. Legacy profiles are migrated once on first load. Downstream stages (per-job transforms, UI section editing) are planned for subsequent sub-projects.
- **Profile Schema Engine (sub-project #2 — tree-driven builder UI).** A React editor under `react-dashboard/src/components/widgets/profile-tree/` renders and mutates the tree directly: `ProfileTreeEditor.jsx` (load `GET`/save `PUT /api/config/profiles/{id}/tree`, dirty/discard, 422 surfacing), `TreeNode.jsx` (recursive renderer), `treeOps.js` (pure immutable helpers), `fieldWidgets.jsx` (per-kind inputs), `structuralControls.jsx`, `SectionGallery.jsx` + `sectionCatalog.js` (add sections from templates/Blank). Sections and list entries support rename (double-click), reorder (dnd-kit drag handles), add/remove, visibility (👁), and lock (🔒). The editor is hosted in `ProfileEditorModal` opened from the user's name. Backend tree caps/validation: `validate_tree_limits` (≤500 nodes/≤6 deep, 422) and in-place overlay writes (`apply_flat_to_tree`/`merge_flat_into_stored`) that preserve node ids.
- **Profile Schema Engine (sub-project #3 — schema-driven generation + section/item prompts).** `core/section_generator.py` adds "Model 2": one focused LLM call per unlocked section, authoring fields keyed by node id. Authoring is steered by **section/item prompts** (`prompt` on `SectionNode`/`GroupNode`) assembled by `build_section_prompt` into a canonical folded form `[Section: … [Item: …]]`, mirrored byte-for-byte in JS by `buildFoldedPreview`. Prompts carry **context-injection tokens** — `{profile:<nodeId>}` (rename-safe) and `{job.<field>}` — resolved server-side by `resolve_profile_tokens` + `_apply_template`. Prompts are authored in `PromptEditorModal` (the sole prompt surface): a two-column pill editor whose right-hand tray exposes draggable context **folders** (a section/entry folder injects the whole node) and field chips. **Lock gating** nests: a locked section/entry/field is never sent to the LLM and renders verbatim; a list section whose entries are all locked shows as effectively locked. `tree_to_legacy` now honors `visible` (invisible sections/entries/fields are dropped from the projected document). Generation is currently **dev-only** (admin compare harness `POST /api/dev/resume-compare/{job_key}` in `web/routers/dev.py`); custom/added sections are storable and editable but do **not** yet render on produced résumés/cover letters — that is sub-project #4 (schema-driven rendering).
- **ATS gate + apply hard-block.** `core/ats_gate.py` adds a two-layer ATS parseability check over the rendered résumé PDF: a deterministic mechanical layer (contact order, section presence, required-skill survival, glyph-junk, text-layer) that hard-blocks on any critical issue, and an LLM-powered semantic roundtrip check (advisory). `POST /api/jobs/{key}/confirm-applied` (`web/routers/tray.py`) runs the gate at apply time, returning HTTP 409 on a critical failure and HTTP 422 if artifacts are missing. A DOCX résumé export (via pandoc, résumé-only) is also produced as an alternate artifact and stored as `resume_docx_path` on the job row. The résumé HTML template (`generator/master.css`) received a single-column flex-wrap fix to the header so the contact line renders correctly in both PDF and DOCX export.

## Credits & Metering

Prepaid **fixed-unit** pricing (2026-07-16 rework; replaced the earlier
cost×rate post-paid model below): every billable action has a fixed integer
price in credits, debited **upfront** before the LLM call runs, and refunded
on failure — balances can never go negative and prices no longer depend on
the actual LLM cost incurred. The `credit_ledger` table (append-only:
`profile_id, delta, reason, action, job_key, raw_cost_usd, meta, created_by,
created_at`) is still the **source of truth**; `account.credit_balance` is a
cached running total kept in sync with each ledger insert.

**Price card** (`core/pricing.py` `price_for(action)`, each `PRICE_<ACTION>`
env-overridable): `intake` 2u (score + extract + skill-match bundle),
`generate_fresh` 4u (first generation of a doc_type for a job — a standard
job with resume+cover = 10u total with intake), `regenerate` 2u (re-generation
or feedback-refine of an existing doc), and 1u each for `score`, `extract`,
`resume_parse`, `ats`, `rematch`, `draft`. `unit_usd()` (`CREDIT_UNIT_USD`,
default $0.02) is the dollar value of one unit, used only by the pack
calculator below — it does not affect debits. `resolve_generate_action(db,
job, doc_type)` derives `generate_fresh` vs `regenerate` server-side from
whether a `Document` row (or a stored output path) already exists for that
job/doc_type — never trusted from the client.

**Metering chokepoint.** `core/metering.py` `meter_action(db, profile_id, *,
action, job_key, price=None)` wraps a billable action. If the account is
metered (an `Account` row exists, not admin, `credit_rate > 0`): it debits the
action's fixed price via `core.credits.debit_fixed` — a single atomic
conditional `UPDATE` that only succeeds if the balance covers the price,
raising `InsufficientCredits(balance, price, action)` otherwise (`web/main.py`
maps this to HTTP 402 `{error:"insufficient_credits", balance, price,
action}`) — **before** the body runs. It then opens a per-action accumulator;
every `call_llm`/`record_usage` call inside the body appends its real cost.
On success it annotates the already-settled debit row with the summed raw
cost + call metadata (models, token counts) for margin tracking — this never
changes what was charged. On any exception it refunds the debit
(`refund_debit`, a compensating `+price` ledger row) before re-raising.
Unmetered accounts (no `Account` row, or `credit_rate == 0`, the developer
tier) run the body ungated and are never debited. A content-free `credits` SSE
event nudges the dashboard to refetch balance on both debit and refund.

**Metering topology:** the intake pipeline debits **one** `intake` (2u) around
extract + score + skill-match; the generate endpoints resolve
`generate_fresh` (4u) vs `regenerate` (2u) via `resolve_generate_action` and
bundle the post-gen eval/refine turns under that same debit (ATS is free when
it's part of a generate flow); standalone `score`/`extract`/`rematch`/
`resume_parse`/`draft` endpoints are 1u each; the ATS gate is metered (1u)
only when it's re-triggered by a manual document edit outside a generate
flow; the feedback-refine endpoint is **one** `regenerate` (2u) meter with a
fail-fast balance pre-check on its 202 (fire-and-forget) entry point. All
failed/no-op action paths (including tree-v1 generation failures) are
refunded.

**Grants.** New accounts receive a signup grant sized by tier
(`core.credits.signup_grant_for_tier(tier)`, env `CREDIT_SIGNUP_GRANTS` JSON
map, defaults `standard` 20 / `friends_family` 50 / `beta` 200 units) at
provisioning, reason `signup_grant`. `POST /api/admin/credits/grant`
(`web/routers/credits.py`, admin-only) grants credits by profile_id or email
with reason `admin_grant` — the same call the Stripe webhook (Payments,
below) reuses for purchased credit packs.

**Redenomination.** Alembic migration `aa10units01` is a one-shot conversion
of all existing balances from the old cost-based credit denomination to the
new unit denomination (÷20), inserting `redenomination` ledger rows for the
adjustment; non-admin accounts that never made a purchase also receive a
`redenomination_topup` grant up to their tier's signup amount. The downgrade
is a no-op (the old denomination isn't reconstructable). This runs exactly
once, automatically, via the existing `alembic upgrade head` on Railway
startup.

**Retired:** `credit_floor`/`debit_for_action`/`to_credits`/
`signup_grant_amount` (post-paid cost×rate helpers) and `tier_margins`
(purchase-side margin table) are deleted; `CREDIT_FLOOR`,
`CREDIT_SIGNUP_GRANT`, `CREDIT_DEFAULT_RATE` (rate itself still exists on
`Account` but is no longer read for debit sizing), and `CREDIT_TIER_MARGINS`
no longer do anything and should be removed from deployed env if set.

## Payments

Stripe Checkout sells credit packs via server-side redirect (no client-side
Stripe.js). Pack sizing is **unit-denominated**: `core/payments.py` computes
`credits = net(price_usd) / unit_usd() × tier_multiplier × (1 + bulk_discount)`
— net proceeds (price minus the Stripe fee model + tax buffer) converted to
units at `unit_usd()` (`core/pricing.py`, default $0.02/unit), then scaled by
the buyer's tier multiplier and the bulk discount for that price point.

**Tiers** (`account.tier`, `purchase.tier`): `standard` (1×), `friends_family`
(4×), `beta` (10×) — `core/payments.py` `tier_multipliers()`, env
`CREDIT_TIER_MULTIPLIERS` JSON override. The old purchase-side `tier_margins`
table is retired.

`core/payments.py` is a pure pricing **calculator** (no Stripe calls):
`tier_multipliers()`, `price_tiers()` (bulk discount per dollar amount: $1→0,
$5→5%, $10→10%, $20→15%), `tier_visibility()` (beta sees only $1;
friends_family/standard see $1/$5/$10/$20), `price_ids()` (dollar→Stripe price
id from `STRIPE_PRICE_IDS`), `compute_credits(price_usd, tier)`, and helpers
`packs_for_tier`/`resolve_price_id`. Stripe stores only the **4 dollar
prices** ($1/$5/$10/$20 under one "Auto Apply Credits" product); credits are
always computed server-side per tier (never trusted from the client). The
admin `grant-budget` stat is likewise converted to unit denomination.

`core/stripe_client.py` thinly wraps the `stripe` SDK (v15.2.1):
`create_customer`, `create_checkout_session`, `retrieve_price`,
`construct_event` — all reading `STRIPE_SECRET_KEY`/`STRIPE_WEBHOOK_SECRET`
from env lazily.

**Schema:** the `purchase` table (`db/database.py`, Alembic `aa01payments01`)
records `profile_id, stripe_session_id [unique], stripe_event_id [unique,
idempotency key], price_id, credits, amount_usd, status (pending|completed),
created_at`; `account.stripe_customer_id` caches the Stripe customer per
tenant (created on first buy).

**Routes (`web/routers/payments.py`, `/api/payments/*`):**
- `GET /packs` — packs visible to the caller's tier with server-computed
  credits (`payments.packs_for_tier`, no Stripe call).
- `POST /checkout` (auth-gated) — resolves the price against the buyer's tier,
  computes credits server-side, creates the Stripe customer if needed, records
  a `pending` `Purchase` (storing `tier` + `credits`), returns the session URL.
- `POST /webhook` — Stripe callback, signature-verified
  (`stripe_client.construct_event`); on `checkout.session.completed`, marks
  the matching `Purchase` `completed` and grants credits via
  `core.credits.grant_credits(reason="purchase")`. Idempotent on
  `stripe_event_id` (duplicate deliveries are no-ops).
- `GET /history` — the caller's recent purchases.

The webhook is unauthenticated by design (Stripe can't present a session
cookie) — `web/auth/middleware.py` adds `/api/payments/webhook` to
`_EXEMPT_PATHS`, relying entirely on signature verification for security.

**New env vars:** `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`,
`STRIPE_PRICE_IDS` (JSON map `dollar amount -> Stripe price id`; replaces the
retired `STRIPE_PACKS`), `APP_BASE_URL` (base URL for Checkout success/cancel
redirects). Optional pricing overrides: `CREDIT_TIER_MULTIPLIERS`,
`CREDIT_PRICE_TIERS`, `CREDIT_TIER_VISIBILITY` (JSON), `CREDIT_UNIT_USD`,
and `STRIPE_FEE_PCT`, `STRIPE_FEE_FIXED`, `TAX_RATE` (floats).

**Admin:** `POST /api/admin/credits/tier` (admin-only, `web/routers/credits.py`)
sets a profile's tier (target by `profile_id` or `email`; validated against
`payments.tier_multipliers()`).

**Known limitation:** refunds are not handled — a Stripe refund does not
claw back granted credits; reversal is admin-manual only.

## Key Invariants

- `Job` LLM methods receive an already-constructed client + model string; they do not read config themselves.
- DB writes inside `Job` methods use the caller-supplied session; callers own commit/rollback (except `Document.upsert`, which commits).
- The `documents` table is the source of truth; `.md` and PDF are derived artifacts and are never hand-edited.
- Structured résumé generate/refine route through `_llm_json_with_retry`; `_refine_doc_md` uses `max_tokens=32768` to avoid truncation.

## Deployment (Railway)

The app deploys as one Railway service built from the repo-root `Dockerfile`
(multi-stage: Node builds the React SPA, Python runtime adds pandoc + Playwright
Chromium and runs `uvicorn web.main:app --host 0.0.0.0 --port $PORT
--proxy-headers --forwarded-allow-ips="*"`). The proxy flags are required: behind
Railway's TLS-terminating proxy they let uvicorn trust `X-Forwarded-Proto: https`
so `request.url_for()` builds **https** OAuth callback URLs — without them the
callback goes out as `http://…` and Google/GitHub reject it as
`redirect_uri_mismatch`.

**Database:** Railway-managed Postgres. `DATABASE_URL` is auto-normalized to the
psycopg3 driver (`db.database._normalize_db_url`). Schema is created/upgraded on
startup by `init_db()` → `alembic upgrade head`; a fresh Postgres self-migrates
on first boot. (To port existing local SQLite data, run
`scripts/port_sqlite_to_pg.py` separately — not part of normal deploy.)

**Access:** Google/GitHub OAuth (`web/auth/`). Sessions are signed cookies
(`SESSION_SECRET`). The tenancy seam (`web.tenancy.current_profile_id`) resolves
the logged-in account's profile in production. A pure-ASGI gate
(`web/auth/middleware.py`) 401s unauthenticated `/api/*` requests; the SPA shell
loads unauthenticated and shows a login screen when `/api/me` returns 401.
Access is invite-gated by `ALLOWED_EMAILS`; `ADMIN_EMAILS` bypass it and the
first admin login claims the existing `profile_id=1`. `GET /health` is exempt
for the platform healthcheck. Provider redirect URIs to register:
`https://autoapply.matthewbarlow.me/auth/callback/google` and `…/github`.

**Persistent files:** a Railway volume mounted at `/data` with `DATA_DIR=/data`.
Generated documents and uploaded resumes (via `core/paths.py`) live under it.

**Secrets / config:** all via Railway environment variables. Runtime `.env`
key-writing is disabled when `APP_ENV=production`.

**Required environment variables:**

| Var | Value |
|---|---|
| `DATABASE_URL` | Railway Postgres URL |
| `LLM_PROVIDER_TYPE` | `openrouter` \| `anthropic` \| `openai` \| `gemini` |
| `LLM_API_KEY` | platform LLM key |
| `LLM_DEFAULT_MODEL` | default model id |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Google OAuth app creds |
| `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` | GitHub OAuth app creds |
| `SESSION_SECRET` | random secret for signed session cookies |
| `ALLOWED_EMAILS` | comma-separated beta allowlist |
| `ADMIN_EMAILS` | comma-separated admin/owner emails |
| `DATA_DIR` | `/data` |
| `APP_ENV` | `production` |
| `PORT` | provided by Railway |

**Railway service settings:** build from Dockerfile; healthcheck path `/health`;
attach a volume at `/data`.

**Not deployed:** the tray app and browser extension remain local clients.

## Roadmap: SaaS conversion (planned — not yet built)

The app is being converted to a multi-user SaaS in four sequenced sub-projects,
each with its own spec → plan → implementation cycle (designs under
`docs/superpowers/`, status in `.claude/TODO.md`). The multi-tenancy foundation is
already in place (see "Tenant scoping" in `db/CONTEXT.md`); these layer on top:

1. **Auth & Identity** *(implemented)* — Google/GitHub OAuth via Authlib +
   Starlette signed-cookie sessions. Adds `account` + `identity` tables (one
   account = one `user_profile`/tenant, linked by verified email).
   `web.tenancy.current_profile_id` resolves the logged-in account's profile in
   production; a pure-ASGI gate on `/api/*` (`web/auth/middleware.py`) replaced
   the HTTP Basic gate; access is invite-gated by `ALLOWED_EMAILS`.
   Spec: `docs/superpowers/specs/2026-06-11-auth-identity-design.md`.
2. **Credits & Metering** *(implemented)* — per-tenant `credit_ledger` +
   cached `account.credit_balance`/`credit_rate`; `meter_action` gates and
   debits score/generate/eval/refine/extract; `GET /api/credits` +
   admin grant/system-balance endpoints. See "Credits & Metering" above.
3. **Payments** *(implemented)* — Stripe Checkout for credit packs + webhook →
   credit grants via `grant_credits(reason="purchase")`. See "Payments" above.
4. **Onboarding UX rework** *(in progress)* — the API-key step is dropped: the
   welcome wizard is now a single "Upload Master Resume" modal triggered on first
   login (no parsed résumé), parsing against the auto-provisioned profile using
   the platform key and the account's tiered signup credit grant
   (`signup_grant_for_tier`, env `CREDIT_SIGNUP_GRANTS`). `setup-status.llm_configured` counts the platform
   `LLM_API_KEY` so credit-gated actions aren't blocked. After the wizard, a
   single **action-gated guided tour** (react-joyride; `react-dashboard/src/
   components/Onboarding/`, `TOUR_STEPS`) walks the user through the profile
   editor, job inbox, scoring, and generation. It drives against a pre-seeded
   **demo job** (`core/demo_data.py` `seed_demo_job`, inserted pre-scored at
   profile creation so no LLM call is needed) and persists progress via
   `PATCH /api/onboarding/tour` (`web/routers/onboarding.py`) →
   `user.onboarding_tour`.
   Specs: `docs/superpowers/specs/2026-06-15-resume-first-onboarding-design.md`,
   `…/2026-07-06-onboarding-guided-tour-design.md`. Still open: surface the
   credits/buy flow in onboarding, and close the *automated* job-ingestion gap
   (a manual paste path exists and auto-scores; the browser extension still
   points at localhost and the API scrapers are dormant).
