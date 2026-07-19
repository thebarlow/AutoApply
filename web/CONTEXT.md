# web/ Context

FastAPI backend. Serves the REST API on port 8080. The frontend (React) is a separate Vite app in `react-dashboard/` — this module does **not** serve HTML.

## Architecture

```
web/
├── main.py                       # FastAPI app; includes all routers; registers AuthGate + Session middleware
├── tenancy.py                    # current_profile_id seam (session in prod / dev stub otherwise) + scoped(); honors impersonation (see Auth below)
├── middleware_impersonation.py   # ImpersonationReadOnlyMiddleware — blocks unsafe methods while impersonating (see Auth below)
├── sse.py                        # Server-Sent Events helpers (tenant-scoped job update broadcasts)
├── llm_status.py                 # In-memory tracker for active LLM jobs (keyed by job_key+action)
├── intake_pipeline.py            # Post-ingest pipeline (score + generate) run per new job
├── static/images/                # Favicon and apple-touch-icon (served by FastAPI)
├── auth/
│   ├── identity.py          # Pure logic: Claims, resolve_or_provision_account, beta gate, provisioning
│   ├── routes.py            # Google/GitHub OAuth login/callback/logout + GET /api/me; _fetch_claims (provider I/O)
│   └── middleware.py        # Pure-ASGI prod gate: 401s unauthenticated /api/* (SSE-safe)
└── routers/
    ├── jobs.py              # Core job endpoints: CRUD, score, generate resume/cover, serve PDFs
    ├── scraper.py           # POST /api/scraper/stage-job (browser ext); POST /api/scraper/search + GET /last-search + POST /scrape-selected (Find Jobs tab: preview/persist API-scraper candidates)
    ├── config.py            # GET/PUT config key-value (per-tenant → profile_config; global infra → config)
    ├── prompts.py           # GET/PUT per-profile prompt overrides
    ├── llm_status_router.py # GET /api/llm/status (active LLM job status)
    ├── session_cost_router.py # GET /api/session-cost (cumulative LLM token spend)
    ├── setup_status.py      # GET /api/setup-status (onboarding completeness: llm_configured | resume_parsed | onboarding_tour)
    ├── onboarding.py        # PATCH /api/onboarding/tour (persist guided-tour progress; validated state machine)
    ├── credits.py           # GET /api/credits, POST /api/admin/credits/grant, POST /api/admin/credits/tier, GET /api/admin/system-balance; require_real_admin dependency (session-based admin gate, shared by admin.py/dev.py)
    ├── admin.py             # Admin-only endpoints: invites + user management + impersonation (see Routing Rules and Auth below)
    ├── payments.py          # GET /api/payments/packs, POST /checkout, GET /verify, POST /webhook (Stripe), GET /history
    ├── stats.py             # GET /api/stats (pipeline activity by time window) + GET /api/skill-frequency; exposes invalidate_skill_cache()
    ├── skills.py            # /api/skills/aliases* (synonym groups) + /api/skills/profile (active-profile skill add/remove)
    ├── tray.py              # Tray app integration endpoints
    ├── events.py            # SSE endpoint (/api/events)
    └── docs_router.py       # Serves Obsidian markdown docs as JSON; tier-gates docs via a 'tiers:' frontmatter key
```

## Routing Rules

| Task | File |
|---|---|
| Job CRUD, scoring, resume/cover generation | `routers/jobs.py` |
| Ingesting a job from the browser extension, or searching/staging API-scraper candidates (Find Jobs tab) | `routers/scraper.py` |
| Pipeline activity stats by time window | `routers/stats.py` |
| Skill frequency across extracted jobs | `routers/stats.py` (delegates to `core/skill_analytics.py`) |
| Skill alias groups + marking profile skills | `routers/skills.py` (invalidates `stats.py` skill cache on mutation) |
| Session LLM cost tracking | `routers/session_cost_router.py` |
| Credit balance / history, admin grants, system balance | `routers/credits.py` |
| Stripe Checkout (packs/checkout/verify/webhook/history) | `routers/payments.py` |
| App config key-value (scoring weights, templates, scraper prefs, legacy prompt-picker) | `routers/config.py` — per-tenant keys via `_get`/`_set` (`profile_config`); global infra keys via `_get_global`/`_set_global` (`config`) |
| Prompt template get/set per profile | `routers/prompts.py` |
| Active LLM task status (for UI polling) | `routers/llm_status_router.py` |
| Onboarding/setup state | `routers/setup_status.py` |
| Onboarding guided-tour progress (PATCH) | `routers/onboarding.py` |
| Tray app job card data | `routers/tray.py` |
| Real-time job update stream | `routers/events.py` |
| Documentation content for Docs page | `routers/docs_router.py` |
| OAuth login/callback/logout, `/api/me`, identity provisioning | `auth/routes.py` + `auth/identity.py` |
| Production `/api/*` access gate | `auth/middleware.py` |
| Admin invite management (send invites, list invites) | `routers/admin.py` |
| Admin user management (list users, purchase history) | `routers/admin.py` |
| Admin impersonation (start/stop read-only view-as) | `routers/admin.py` + `middleware_impersonation.py` |

## Key Design Notes

- **Access control (Auth sub-project — DONE & live)** — the hosted instance uses **Google/GitHub OAuth** (`web/auth/`, Authlib + Starlette signed-cookie sessions). Flow: `GET /auth/login/{provider}` → provider → `GET /auth/callback/{provider}` calls `_fetch_claims` (the only provider-I/O function, mocked in tests) → `resolve_or_provision_account` (returning user → existing account; new provider on a known verified email → linked identity; new email → provisioned `account`+`user_profile` with seeded prompts/aliases). Beta-gated by `ALLOWED_EMAILS`; `ADMIN_EMAILS` bypass it and the **first admin login claims the existing `profile_id=1`** (carries over current data). Session holds `account_id`; `GET /api/me` returns `{email,is_admin,profile_name}` or 401. `web/auth/middleware.py` (pure ASGI, so the `/api/events` SSE stream isn't buffered) 401s unauthenticated `/api/*` **in production only** — `/health`, `/auth/*`, the SPA shell, and static assets pass so an unauthenticated browser can load the login screen. `web/tenancy.py` `current_profile_id` resolves the session account's profile in production, else the dev stub (→ `Config['dev_tenant_id']`, default 1) so local dev + tests need no login. Middleware order in `main.py`: `SessionMiddleware` is registered **last** (outermost) so `scope["session"]` is populated before the gate runs. The old `web/auth_gate.py` HTTP Basic gate was deleted.
  - **Webhook exemption** — `_EXEMPT_PATHS` includes `/api/payments/webhook` so Stripe's
    unauthenticated callback bypasses the `/api/*` gate; the route is secured entirely by
    `stripe_client.construct_event`'s signature check, not a session.
  - **Runtime invite allowlist** — `is_allowed_email` (`web/auth/identity.py`) checks the `allowed_email` DB table (rows inserted by `POST /api/admin/invite`) in addition to the `ALLOWED_EMAILS` env var, so invites take effect immediately without a redeploy.
  - **Ban / restore** — `account.banned` (bool) is set by `POST /api/admin/users/{id}/access` `{banned}`. All account resolution paths in `web/auth/identity.py` reject a banned account; `web/tenancy.py`'s `current_profile_id` also returns 401 for banned accounts so every API request is blocked. Banning also deletes the target's `allowed_email` row so the account can't re-provision. The endpoint returns 400 if the target is an admin and 404 if unknown. `banned` is included in the `GET /api/admin/users` row shape.
  - **Admin impersonation** — `POST /api/admin/impersonate/start` stores `impersonate_profile_id` in the session. While set, `tenancy.py`'s `current_profile_id` (via the `_impersonated_profile_id` helper) re-verifies the caller is still an admin on every request, then returns the impersonated profile's ID — so all tenant-scoped DB reads transparently re-point to that user. `ImpersonationReadOnlyMiddleware` (`web/middleware_impersonation.py`) blocks all unsafe HTTP methods (POST/PUT/PATCH/DELETE) with 403 `impersonation_read_only` while a session holds `impersonate_profile_id`, with an allowlist for `POST /api/admin/impersonate/stop` and `POST /auth/logout`. The middleware is registered **inside** `SessionMiddleware` in `main.py` so `scope["session"]` is available. Admin endpoints in `routers/admin.py` use a `require_real_admin` dependency that authorizes against `session["account_id"]` directly (bypassing the impersonated profile) so they remain admin-gated while impersonating. `POST /api/admin/impersonate/stop` clears the session key. `GET /api/me` returns `impersonating: {profile_id, email}` when active, `null` otherwise.
  - **Prod requirements:** `SESSION_SECRET` (the app **refuses to boot** in production if unset or left as the dev default — see `_session_secret()` in `main.py`), `GOOGLE_/GITHUB_CLIENT_ID/SECRET`, `ALLOWED_EMAILS`, `ADMIN_EMAILS`. Uvicorn must run with `--proxy-headers --forwarded-allow-ips="*"` (in the Dockerfile CMD) so Railway's `X-Forwarded-Proto: https` is trusted and `request.url_for()` builds **https** OAuth callback URLs — otherwise providers reject `http://` callbacks as `redirect_uri_mismatch`.
- **Score/generate are in `core/job.py`** — `routers/jobs.py` resolves the LLM client, prompt content, and template paths, then delegates to `job.score()`, `job.generate_resume_md/pdf()`, `job.generate_cover_md/pdf()`.
- **Generation is synchronous** — resume/cover generation blocks the request 30–60s while Claude + pandoc run. Acceptable for single-user local use.
- **SSE for real-time updates** — `sse.py` broadcasts job state changes; `App.jsx` subscribes via `EventSource`. **Tenant-scoped:** `subscribe(profile_id)`/`send(type, data, *, profile_id=...)` deliver an event only to that tenant's connected clients; `/api/events` subscribes with `current_profile_id`. Pass `profile_id=None` only for genuinely global events (e.g. platform LLM up/down). Job/credits/prompt_reset/llm_status events must always be scoped — the payloads are tenant-private and `job_key` is unique only per profile. The `llm_status` registry is keyed by `(profile_id, job_key)` for the same reason.
- **`llm_status.py`** tracks in-progress LLM calls (start/finish) so the UI can show spinners without polling.
- **Structured document editing (Phase 3b)** — `GET /api/jobs/{job_key}/{doc_type}/document` returns the stored structured JSON; `PUT` validates the body against a Pydantic `ResumeDocument`/`CoverDocument`, upserts the `Document` row, re-assembles the `.md`, and re-renders the PDF. Errors: `400` invalid `doc_type` or validation failure, `404` missing job or document, `500` render failure after the document was persisted. The old raw-Markdown editor bridge (`PUT .../markdown` and helpers `_put_document_markdown_sync` / `_read_body_text`) was retired.
- **Parse-on-read backfill (not persisted).** When `GET .../document` finds no `documents` row, it reconstructs the document from the on-disk `.md` (`core/document_parser`) and returns it **without persisting** — the `.md` stays authoritative and parser improvements always apply. A row is created only by a write: `PUT .../document` (edit) or a feedback refine. `POST .../feedback` must mutate+re-persist a structured doc, so it calls `_ensure_document_row` to backfill **and persist** a row from the `.md` first; it `404`s only when there's neither a row nor a `.md`.
- **Per-turn refinement snapshots** are written as structured JSON `{job_key}_{doc_type}_turn_{n}.json` in `generator/outputs/`. `GET /api/jobs/{job_key}/{doc_type}/turn/{n}/markdown` assembles Markdown on the fly from that JSON (`422` on schema mismatch).
- **Credits & Metering (prepaid fixed-unit pricing, 2026-07-16 rework — DONE)** — every billable action has a fixed integer price in credits (`core/pricing.py` `price_for(action)`: `intake=2, generate_fresh=4, regenerate=2, score/extract/resume_parse/ats/rematch/draft=1`, each `PRICE_<ACTION>`-overridable), debited **upfront** via `core.credits.debit_fixed` (one atomic conditional `UPDATE`, balance can never go negative) before the action body runs, and refunded (`refund_debit`) on any exception. `routers/credits.py`: `GET /api/credits` returns the caller's `{balance, rate, recent[]}` (last 20 ledger rows; `{balance:0, rate:0.0, recent:[]}` if no `Account` row). `require_real_admin` (a FastAPI dependency, defined in `routers/credits.py`; audit S4 — every admin endpoint across `credits.py`/`admin.py`/`dev.py` now uses it) resolves the **real** logged-in account from the session's `account_id` (not `current_profile_id`, which would resolve the *impersonated* tenant mid-impersonation) and 403s unless `is_admin`; outside production it falls back to the dev-tenant account. It gates `POST /api/admin/credits/grant` (target by `profile_id` or `email`, `reason="admin_grant"` — the same `grant_credits` call the Stripe webhook reuses) and `GET /api/admin/system-balance` (reads the platform OpenRouter key's remaining balance via `LLM_API_KEY`, 502 on upstream failure, 503 if unset). `core.credits.InsufficientCredits` is registered in `web/main.py` as an exception handler returning **HTTP 402** `{error:"insufficient_credits", balance, price, action}` (the old `{floor}` payload is retired) — raised by `debit_fixed` inside `meter_action` (see `core/CONTEXT.md` → "Credits & Metering") when the balance can't cover the action's price.
  - **Metering topology**: the intake pipeline debits **one** `intake` (2u) meter around extract + score + skill-match (`intake_pipeline.py`); generate endpoints (`POST /{job_key}/generate/resume`, `POST /{job_key}/generate/cover`, `routers/jobs.py`) resolve `generate_fresh` (4u) vs `regenerate` (2u) via `core.pricing.resolve_generate_action` (server-derived from a `Document` row / stored output path) and bundle the post-gen eval/refine turns under that same debit — ATS is free when it runs as part of a generate flow. Standalone 1u actions: `POST /{job_key}/score`, the ATS gate (`run_ats_gate`, `action="ats"` — metered only when re-triggered by a manual document edit outside a generate flow), `POST /api/config/section-prompt/draft` (`action="draft"`, no `job_key`), `POST .../parse/propose` résumé parsing (`action="resume_parse"`, `config.py`), and `_do_extract_description` / `rematch_skills` (extraction + skill-match, each billed via `record_usage` inside the meter). The feedback-refine 202 endpoint does a fail-fast balance pre-check then meters **one** `regenerate` (2u) for the background turn. Failed actions (including tree-v1 no-op/failure paths) are refunded, never billed.
  - **Grants**: new accounts get a tiered signup grant (`core.credits.signup_grant_for_tier`, env `CREDIT_SIGNUP_GRANTS` JSON, defaults `standard` 20 / `friends_family` 50 / `beta` 200 units). A one-shot Alembic migration (`aa10units01`) redenominated all existing balances ÷20 into the new unit scale on deploy, with `redenomination`/`redenomination_topup` ledger rows for the adjustment (runs once via the existing `alembic upgrade head` startup step).
  - **`/ws/tray` is refused in production** (`routers/tray.py` closes the handshake with 4003 when `APP_ENV=production`): the socket is an unauthenticated process-global singleton for the local desktop tray — websocket scopes bypass `AuthGateMiddleware` (it only gates `scope["type"] == "http"`), so on the hosted instance any client could have held the slot and received other tenants' apply payloads. `POST /{job_key}/apply` consequently always 503s in production.
  - **`GET /api/session-cost` is admin-only in production** — the figure is the process-global (all-tenant) LLM spend; non-admins get `{total: 0.0}` (still 200, since the frontend uses the endpoint as a liveness heartbeat).
  - `credits.py` exposes an `openrouter_remaining()` helper (returns remaining USD or `None`); `GET /api/admin/system-balance` uses it and returns just `{remaining}`. The same helper drives `GET /api/admin/grant-budget`.
  - Frontend: `CreditBalance.jsx` (navbar + User tab) shows balance/rate; a global 402 interceptor shows an "out of credits" toast and the navbar refetches. Admin-only system-balance panel reads `/api/admin/system-balance`. Balance auto-refreshes after a successful metered action: `meter_action` broadcasts a content-free `credits` SSE event on a settled debit, `App.jsx` re-dispatches it as `auto-apply:credits-stale`, and `CreditBalance` refetches its own `/api/credits` (the payload carries no balance because the SSE stream is a global broadcast).
- **Payments (sub-project 3 — DONE)** — `routers/payments.py`: `GET /packs` lists the packs visible to
  the caller's tier with server-computed credits (`core/payments.packs_for_tier`, no Stripe call);
  `POST /checkout` resolves the price against the buyer's tier (`resolve_price_id`), computes credits
  server-side, creates a Stripe customer on first buy, records a `pending` `Purchase` (storing the
  buyer's `tier` + computed `credits`), and returns the Checkout URL; `POST /webhook`
  verifies the Stripe signature, is idempotent on `stripe_event_id`, marks the `Purchase` `completed`,
  and grants credits via `grant_credits(reason="purchase")`; `GET /history` returns the caller's recent
  purchases. Fulfillment is shared by the webhook and `GET /verify?session_id=` via the `_fulfill`
  helper. **Exactly-once is enforced by an atomic conditional claim** — a single
  `UPDATE Purchase SET status='completed' WHERE id=? AND status!='completed'`; only the caller whose
  update matches a row (rowcount 1) grants credits, so concurrent webhook/verify calls or
  double-clicks can never double-credit a payment. The claim and the grant share one transaction (a
  failed grant rolls the claim back → purchase stays pending, retryable). The webhook also keeps its
  `stripe_event_id` pre-check for replays. `GET /verify` is the success-redirect
  fallback: `success_url` carries `&session_id={CHECKOUT_SESSION_ID}`, the browser hits `/verify` on
  return, which retrieves the session, confirms `payment_status == "paid"`, checks tenant ownership,
  then fulfills. This covers **local dev (Stripe's webhook can't reach localhost without
  `stripe listen`)** and delayed/missed webhooks in prod. Frontend: credits are bought from the
  **Settings widget** — `CreditBalance.jsx` `variant="settings"` renders a centered, clickable
  `{n} credits` under the user name in `UserHome.jsx` that opens `BuyCreditsModal.jsx` (closes on Esc
  or backdrop click); `Navbar.jsx` calls `verifyPurchase` on the `purchase=success` redirect, then
  dispatches `credits-stale` + `purchase-success`. The navbar no longer shows credits or a buy button.
  **Known limitation:** refunds are admin-manual only — no automatic credit clawback on a Stripe refund.
- **Extension auth (sub-project A)** — the browser extension runs OAuth via
  `identity.launchWebAuthFlow` against `/auth/ext/login/{provider}`; the callback mints
  a long-lived revocable opaque token (`extension_token` table, sha256-hashed) for an
  EXISTING account only (`resolve_existing_account` — no provisioning, Option B) and
  302s it to the allowlisted `redirect_uri` in a `#token=` fragment. The token rides
  `Authorization: Bearer` on `/api/scraper/stage-job` (resolved by
  `bearer_or_session_profile`, falling back to the session/dev-stub locally).
  `/api/scraper/stage-job` and `/api/ext/me` are in the cookie-gate `_EXEMPT_PATHS`.
  **Stateless flow:** the Starlette session cookie set by `/auth/ext/login` does NOT
  reliably survive `launchWebAuthFlow`'s round-trip, so ext-mode is carried in the OAuth
  `state` (HMAC-signed with `SESSION_SECRET` via `sign_ext_state`/`verify_ext_state`),
  reusing the registered `/auth/callback/{provider}`. The callback detects a valid signed
  state, does a manual token exchange (`_ext_fetch_claims`, no Authlib session), and
  branches to the ext path; otherwise the unchanged website Authlib flow runs.

- **Docs tier-gating (`routers/docs_router.py`)** — `GET /api/docs` (list) and
  `GET /api/docs/{filename}` (content) resolve the caller's `(tier, is_admin)` from the
  `Account` row (via `get_db` + `current_profile_id` deps; defaults to `standard`/non-admin
  when no account). A doc's optional `tiers:` frontmatter key (comma-separated) restricts
  visibility: gated docs are filtered from the list and return **403** on direct fetch unless
  the caller's tier is listed or they're an admin. Docs with no `tiers:` key are public.
  `Browser Extension.md` is gated to `friends_family, beta`; frontmatter is stripped before
  serving content.

## Known caveats (Phase 3b)

- **`PUT .../document` is not transactional across DB and disk (by design).** `Document.upsert` commits the structured edit *before* the `.md`/PDF are re-rendered. If rendering then fails, the route returns `500` but the structured doc is **kept** — deliberately, so the user's edits are not lost and they can trim oversized content and re-save. The on-disk PDF may be stale until the next successful save (it self-heals on re-save). Do not "fix" this by restoring the previous JSON on failure — that would discard the user's edit.
- **`_save_turn_snapshot` silently skips a turn if no `Document` row exists** for the job/doc_type (logs a warning, writes no `.json`). `_restore_best` then ignores that turn. In practice the refine writer commits the row before the loop snapshots it, so this only surfaces under unexpected ordering; the warning print is the debugging hook.

## Known caveats (skill aliases)

- **Renaming a *built-in* alias group leaves a stale self-row.** Seeding creates a self-row per
  curated canonical (e.g. `javascript -> JavaScript`). Reassigning a member like `js` to a new
  canonical (`ECMAScript`) does **not** migrate the seeded `javascript` self-row, so `JavaScript`
  tokens stay in the old group. Merging built-in groups wholesale isn't supported yet; a future
  fix would reassign all rows sharing the old canonical. User-created groups are unaffected.
- **`assign` resolves a typed canonical to an existing alias key's group** (so POSTing
  `canonical:"react"` when `react -> React` exists adopts `React`), preventing accidental
  lowercase forks. The autocomplete normally feeds real canonicals, so this is a safety net.
- **`search_aliases` is a full table scan per keystroke.** Fine for a modest alias table; add a
  `LIKE`/index if users import large synonym sets.

## API Surface

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/jobs` | All jobs ordered by `final_score` desc |
| `DELETE` | `/api/jobs/{job_key}` | Hard delete |
| `PATCH` | `/api/jobs/{job_key}/state` | State transition; stamps `applied_at` (UTC ISO) on the first transition into `APPLIED` — preserved on re-entry — so the User-tab stat counter (counts by `applied_at`, not state) sees dashboard-applied jobs. The tray app's `Job.mark_applied` stamps it too |
| `POST` | `/api/jobs/{job_key}/score` | Score job via LLM |
| `POST` | `/api/jobs/{job_key}/generate/resume` | Generate resume MD + PDF |
| `POST` | `/api/jobs/{job_key}/generate/cover` | Generate cover letter MD + PDF |
| `GET` | `/api/jobs/{job_key}/resume` | Serve resume PDF |
| `GET` | `/api/jobs/{job_key}/cover` | Serve cover letter PDF |
| `GET` | `/api/jobs/{job_key}/{doc_type}/document` | Return the stored structured document JSON (`ResumeDocument`/`CoverDocument`); if the `documents` row is missing, reconstructs it on the fly from the on-disk `.md` (via `core/document_parser`) **without persisting**, else `404` |
| `PUT` | `/api/jobs/{job_key}/{doc_type}/document` | Upsert an edited structured document; re-assembles `.md` + re-renders PDF |
| `POST` | `/api/jobs/{job_key}/{doc_type}/feedback` | Accept user section/item feedback (`{notes:[{section,label,note}]}`); ensures a `documents` row exists, backfilling+persisting from the `.md` if needed (`_ensure_document_row`); `404` if no row and no `.md`; drops empty notes (`400` if none); spawns `run_user_feedback_refine` background job (reuses refine path, eval-for-score, no restore-best, résumés trigger ATS gate); appends a Refinement-History turn tagged `source="user_feedback"`; returns 202 + job |
| `POST` | `/api/scraper/stage-job` | Ingest job from browser extension or scraper |
| `POST` | `/api/scraper/search` | Body `{query, exclude:[], location:""}`; runs `search_sources` (Remotive + RemoteOK) with banned-word `exclude` + optional `location` filter, returns `{query, candidates:[{...ScrapedJob, candidate_id}]}`. Each candidate gets a stable `candidate_id` (sha1 of title/company/location); candidates already in this profile's inbox/archives (non-deleted) are **excluded** entirely. Persists `query`/`exclude`/`location` to `profile_config`; candidates are NOT persisted |
| `GET` | `/api/scraper/last-search` | Returns `{query, exclude:[], location}` — the profile's remembered search + filters |
| `POST` | `/api/scraper/scrape-selected` | Body `{jobs:[...]}`; batched intake of user-selected candidates — saves, runs `intake()` + `run_pipeline()` (threaded, SSE-updated); returns `{results:[{job_key, status: staged|duplicate}]}` |
| `GET` | `/api/stats` | Pipeline activity bars + by-state counts (window param) |
| `GET` | `/api/skill-frequency` | Combined required+preferred skill counts (`skills`) plus `tech_stack`, distinct jobs, across all extracted jobs; no window. Also returns `profile_skills` (active user's skills, normalized) so the UI can flag covered skills. The job aggregation is cached in-process keyed by extracted-job count with a 60s TTL — a re-extraction that doesn't change the count can be up to 60s stale; tests reset `stats._SKILL_CACHE` via an autouse fixture. |
| `GET` | `/api/skill-frequency/jobs` | Job keys whose extraction data lists a given `skill` (normalized, any field) |
| `GET` | `/api/skills/aliases` | All alias groups `[{canonical, members}]` |
| `GET` | `/api/skills/aliases/search` | Canonicals matching `q` (substring over canonical + members) |
| `POST` | `/api/skills/aliases/assign` | Add/move `skill` into a group `canonical` (creates group if new) |
| `DELETE` | `/api/skills/aliases/member` | Remove `skill` from its group (`400` if it's the canonical self-row) |
| `POST/DELETE` | `/api/skills/profile` | Add/remove `skill` on the active profile (case-insensitive dedup) |
| `POST` | `/api/skills/owned` | Given `{skills:[…], job_key?}`, return the subset the active profile owns (alias + case aware, plus any skill in the job's cached `ext_skill_match` `matched` set when `job_key` is supplied; also recovers ownership when an owned skill key appears as a bounded word inside a multi-word phrase, e.g. a verbose `"Strong proficiency in Python"` extraction entry — guards against false résumé-gap chips); echoes input strings |
| `POST` | `/api/jobs/{job_key}/rematch-skills` | Re-run the semantic skill matcher for a job (credit-metered like extract); updates `ext_skill_match` in-place and SSE-broadcasts the job |
| `GET` | `/api/session-cost` | Cumulative LLM token cost for current session |
| `GET` | `/api/credits` | Caller's `{balance, rate, recent[]}` (last 20 ledger rows) |
| `POST` | `/api/admin/credits/grant` | Admin-only; grant credits to a profile by `profile_id` or `email`, reason `admin_grant` |
| `POST` | `/api/admin/credits/tier` | Admin-only; set a profile's pricing tier (target by `profile_id` or `email`; validated against `payments.tier_multipliers()`) |
| `GET` | `/api/admin/system-balance` | Admin-only; remaining balance on the platform OpenRouter key (`{remaining}` USD) |
| `POST` | `/api/admin/invite` | Admin-only; normalizes email, idempotently inserts `allowed_email` row, sends invite email via `core.email.send_invite` |
| `GET` | `/api/admin/invites` | Admin-only; list invited emails, **excluding any allowlisted email that already has an `Account`** (registered invitees drop off the Invited list and appear under Users) |
| `GET` | `/api/admin/users` | Admin-only; list all users `[{profile_id, email, tier, credits, is_admin, banned}]` |
| `GET` | `/api/admin/users/{profile_id}/purchases` | Admin-only; purchase history for a specific user; 404 if profile unknown |
| `POST` | `/api/admin/users/{id}/access` | Admin-only (`require_real_admin`); `{banned: bool}` — bans or restores a user; banning also deletes the `allowed_email` row; 400 if target is admin, 404 if unknown |
| `GET` | `/api/admin/grant-budget` | Admin-only (`require_real_admin`); returns `{system_credits, allocated, available}` — `system_credits` = OpenRouter remaining × 1000; `allocated` = sum of non-admin balances; `available` = max(system−allocated, 0); fields are null when the balance is unavailable |
| `POST` | `/api/admin/users/{id}/grant` | Admin-only (`require_real_admin`); `{amount: int}` — grants credits to a user via `grant_credits`; capped at `available` from grant-budget; 409 if balance unavailable (fail-closed), 400 `exceeds_grant_budget` if amount exceeds available |
| `POST` | `/api/admin/impersonate/start` | Admin-only; body `{profile_id}`; sets `impersonate_profile_id` in session; 404 if profile unknown |
| `POST` | `/api/admin/impersonate/stop` | Admin-only (allowlisted through read-only gate); clears `impersonate_profile_id` from session |
| `GET` | `/api/payments/packs` | Configured credit packs with live price/currency from Stripe |
| `POST` | `/api/payments/checkout` | Create a Stripe Checkout session for a pack; records a pending `Purchase`, returns the session URL |
| `GET` | `/api/payments/verify` | Success-redirect fallback fulfillment; confirms `payment_status=="paid"` with Stripe, tenant-checks, then grants (idempotent with the webhook) |
| `POST` | `/api/payments/webhook` | Stripe webhook (signature-verified, unauthenticated — see Auth gate exemption below); idempotent on `stripe_event_id`; grants credits via `grant_credits(reason="purchase")` |
| `GET` | `/api/payments/history` | Caller's recent purchases |
| `GET/PUT` | `/api/config/{key}` | Config key-value store |
| `GET/PUT` | `/api/prompts/...` | Prompt templates per profile |
| `POST` | `/api/llm/test` | Test LLM connectivity |
| `GET` | `/api/llm/status` | Active LLM task status |
| `GET` | `/api/setup-status` | Onboarding completeness (`llm_configured`, `resume_parsed`); `llm_configured` counts the platform `LLM_API_KEY` |
| `GET` | `/api/events` | SSE stream for job updates |
| `GET` | `/auth/login/{provider}` | Start OAuth (`google`/`github`); 404 for unknown provider |
| `GET` | `/auth/callback/{provider}` | OAuth callback; provisions/resolves account, sets session, redirects `/` (or `/?beta=closed`, `/?auth_error=1`) |
| `POST` | `/auth/logout` | Clear the session |
| `GET` | `/api/me` | Logged-in identity `{email,is_admin,profile_name,impersonating:{profile_id,email}|null}`; 401 if no session |
| `GET` | `/auth/ext/login/{provider}` | Start extension OAuth; `redirect_uri` must match `EXTENSION_REDIRECT_URLS` (400 otherwise); ext-mode flag stashed in session |
| `POST` | `/auth/ext/revoke` | Bearer-authed; revoke the presented extension token |
| `GET` | `/api/ext/me` | Bearer-authed; `{email}` of the token's account; 401 if invalid |

## Dev Endpoints (`web/routers/dev.py`)

Admin-gated, dev-only endpoints not intended for production user flows.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/dev/resume-compare/{job_key}` | Run Model 1 (dry, single-call, existing `generate_resume_md` code path) and Model 2 (per-section, `core/section_generator`) against the same job; eval each result with `Job.evaluate_resume_body`; return `{css, model1, model2}` where each model is `{markdown, score, issues, sections}` or `{error}` if that model failed. `sections` is `[{heading, html}]` — the model's assembled Markdown run through pandoc (`core.utils.markdown_to_html`) then split at top-level `<h2>` boundaries (`_split_sections_html`; pre-first-`<h2>` content becomes a leading "Header" section). Top-level `css` is the contents of `generator/resume.css`, used by the UI to render each section in PDF styling. Not metered, no ATS check, no document persistence. Per-model errors are isolated — one model failing does not prevent the other from running (an errored model has no `sections`, but top-level `css` is still returned). |

## Known Issues

- **`parse/apply` trusts `is_onboarding` from the client.** When `proposal.is_onboarding`
  is true, `parse_apply` REBUILDS the profile tree from scratch and replaces the stored
  `profile_tree`. Safe today because intake only fires on empty profiles, but before any
  existing-profile re-parse UI ships, `parse_apply` must re-derive `is_onboarding`
  server-side from stored data (as `parse_propose` already does) — otherwise a stray
  `is_onboarding=true` against a populated profile silently wipes the tree. Guard-rail
  comment is at the branch in `config.py::parse_apply`.
- `_serialize()` in `jobs.py` calls `Path.exists()` twice per job (resume_md_exists, cover_md_exists) on every `GET /api/jobs`. At current scale (<100 jobs) this is negligible. If job count grows, move to a per-job detail endpoint.
- Salary sort is lexicographic for non-numeric salary strings (e.g. "$120k–$150k"). Values without parseable numbers sort as 0.
- **Profile/prompt/setup endpoints must use the tenancy seam, not the legacy dev stub.**
  `/api/setup-status`, all `/api/config/profiles*`, and `/api/prompts/{profile_id}/*` now
  resolve/authorize the tenant via `current_profile_id` (a `{profile_id}` URL ≠ the caller's
  tenant returns 404). Earlier they read the active profile from `Config['dev_tenant_id']` /
  `User.first()` / the raw URL id, which in production served profile 1 to everyone and let
  any tenant read/overwrite/delete another's profile, files, resume-parse, and prompts. When
  adding profile-scoped endpoints, depend on `current_profile_id` — never `dev_tenant_id`.
- **Config is split global vs per-tenant (DONE).** `routers/config.py::_get`/`_set` are
  per-tenant, backed by the tenant-guarded `profile_config` table (composite PK
  `profile_id, key`, seeded from `PROFILE_CONFIG_DEFAULTS`, backfilled for every existing
  profile by Alembic `aa08profcfg01`); `_get_global`/`_set_global` still hit the original
  global `config` table (PK = `key` only). Per-tenant key classes: scoring weights/thresholds
  (`w1`, `w2`, `auto_reject_threshold`, `auto_approve_threshold`, read in
  `web/routers/jobs.py:_load_score_config`), contact links, template paths, and scraper prefs
  (`source_remotive`/`source_remoteok`, `keywords_whitelist/blacklist`,
  `max_jobs_per_source`, `job_searches`, `last_job_search`). Global key classes (deliberately not tenant-scoped):
  `dev_tenant_id` (must stay global — `web/tenancy.py:get_dev_tenant_id` resolves the tenant
  before any tenant is known), migration gates, and `named_providers`/`llm_*`. See
  `docs/superpowers/specs/2026-07-08-config-table-tenancy-design.md` and
  `docs/superpowers/plans/2026-07-08-config-table-tenancy.md`.
- **Prompt-slot models are allowlisted server-side (audit, 2026-07-18).** `PUT
  /api/prompts/{profile_id}/{type_key}` validates `model_override` against
  `core.llm.allowed_models()` (`LLM_ALLOWED_MODELS` env; prod default with it unset =
  `{LLM_DEFAULT_MODEL}` only) and **422s** ("Model not available") anything else — the model
  picker was otherwise a free cost knob against fixed unit prices. `get_client_for_profile`
  also drops disallowed overrides from stale `Prompt` rows. Tests:
  `tests/core/test_model_allowlist.py`, `tests/web/test_prompts_router.py`.
- **Profile file pointers are contained to `profiles/` (audit, 2026-07-18).** Stored file
  pointers (`resume_path`/`md_path`/`cover_letter_path`) are client-settable via
  `PUT /api/config/profiles/{id}` and are read back by the file-serve and résumé-parse sinks, so
  an unguarded pointer let any tenant read arbitrary files on disk (e.g. the platform `.env`). Two
  guards: (1) `_reject_foreign_file_pointers` (called in `update_profile`) **422s** any of those
  keys resolving outside `_PROFILES_DIR` at the write boundary; (2) `serve_profile_file`
  (`GET /api/config/profiles/{id}/file`) re-checks containment (`is_relative_to`) and **404s** a
  pointer outside `profiles/` — defense in depth for any pre-existing poisoned row. When adding a
  new stored file pointer or file-serving route, apply the same containment check.
- **Skills + master-resume export were leaking to profile 1 (audit, 2026-07-18).**
  `POST /api/skills/owned`, `POST /api/skills/profile`, `DELETE /api/skills/profile`, and
  `POST /api/profile/export-master` called `User.load(db)` with no `profile_id`, which defaults to
  profile 1 — so in production every caller read/mutated profile 1's skills and exported profile
  1's résumé. They now inject `current_profile_id` and pass it to `User.load`. Same class as the
  profile/prompt/setup seam item above: profile-scoped work must resolve the tenant via
  `current_profile_id`, never the `User.load` default. Regression tests in `tests/web/test_profile_api.py`.
- **Legacy global prompt-picker REMOVED (audit S1, 2026-07-13).** The old
  `/api/config/prompts/*` CRUD endpoints stored prompt content/templates
  (`{type}_prompts`, `active_{type}_prompt_id`, `{type}_prompt_template`,
  `latex_templates`) in the GLOBAL `config` table with no tenant scoping — any
  tenant's write leaked to every tenant. They were dead (no runtime consumer; live
  generation reads per-tenant prompts from the `prompts` table via
  `User.resolve_prompt()`) and are deleted along with their helpers. Per-tenant
  prompt management lives in `web/routers/prompts.py` (`/api/prompts/*`). Any stale
  global rows in an existing DB are now inert.
