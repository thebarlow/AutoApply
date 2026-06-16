# web/ Context

FastAPI backend. Serves the REST API on port 8080. The frontend (React) is a separate Vite app in `react-dashboard/` — this module does **not** serve HTML.

## Architecture

```
web/
├── main.py                       # FastAPI app; includes all routers; registers AuthGate + Session middleware
├── tenancy.py                    # current_profile_id seam (session in prod / dev stub otherwise) + scoped(); honors impersonation (see Auth below)
├── middleware_impersonation.py   # ImpersonationReadOnlyMiddleware — blocks unsafe methods while impersonating (see Auth below)
├── sse.py                        # Server-Sent Events helpers (job update broadcasts)
├── llm_status.py                 # In-memory tracker for active LLM jobs (keyed by job_key+action)
├── intake_pipeline.py            # Post-ingest pipeline (score + generate) run per new job
├── static/images/                # Favicon and apple-touch-icon (served by FastAPI)
├── auth/
│   ├── identity.py          # Pure logic: Claims, resolve_or_provision_account, beta gate, provisioning
│   ├── routes.py            # Google/GitHub OAuth login/callback/logout + GET /api/me; _fetch_claims (provider I/O)
│   └── middleware.py        # Pure-ASGI prod gate: 401s unauthenticated /api/* (SSE-safe)
└── routers/
    ├── jobs.py              # Core job endpoints: CRUD, score, generate resume/cover, serve PDFs
    ├── scraper.py           # POST /api/scraper/stage-job (browser ext) + POST /api/scraper/run (API scrapers)
    ├── config.py            # GET/PUT config key-value pairs
    ├── prompts.py           # GET/PUT per-profile prompt overrides
    ├── llm_test.py          # POST /api/llm/test (verify LLM connectivity)
    ├── llm_status_router.py # GET /api/llm/status (active LLM job status)
    ├── session_cost_router.py # GET /api/session-cost (cumulative LLM token spend)
    ├── setup_status.py      # GET /api/setup-status (onboarding completeness: llm_configured | resume_parsed)
    ├── credits.py           # GET /api/credits, POST /api/admin/credits/grant, POST /api/admin/credits/tier, GET /api/admin/system-balance; require_admin dependency
    ├── admin.py             # Admin-only endpoints: invites + user management + impersonation (see Routing Rules and Auth below)
    ├── payments.py          # GET /api/payments/packs, POST /checkout, GET /verify, POST /webhook (Stripe), GET /history
    ├── stats.py             # GET /api/stats (pipeline activity by time window) + GET /api/skill-frequency; exposes invalidate_skill_cache()
    ├── skills.py            # /api/skills/aliases* (synonym groups) + /api/skills/profile (active-profile skill add/remove)
    ├── tray.py              # Tray app integration endpoints
    ├── events.py            # SSE endpoint (/api/events)
    └── docs_router.py       # Serves Obsidian markdown docs as JSON
```

## Routing Rules

| Task | File |
|---|---|
| Job CRUD, scoring, resume/cover generation | `routers/jobs.py` |
| Ingesting a job from the browser extension or triggering API scrapers | `routers/scraper.py` |
| Pipeline activity stats by time window | `routers/stats.py` |
| Skill frequency across extracted jobs | `routers/stats.py` (delegates to `core/skill_analytics.py`) |
| Skill alias groups + marking profile skills | `routers/skills.py` (invalidates `stats.py` skill cache on mutation) |
| Session LLM cost tracking | `routers/session_cost_router.py` |
| Credit balance / history, admin grants, system balance | `routers/credits.py` |
| Stripe Checkout (packs/checkout/verify/webhook/history) | `routers/payments.py` |
| LLM provider/model/key config | `routers/config.py` |
| Prompt template get/set per profile | `routers/prompts.py` |
| LLM connectivity test | `routers/llm_test.py` |
| Active LLM task status (for UI polling) | `routers/llm_status_router.py` |
| Onboarding/setup state | `routers/setup_status.py` |
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
  - **Admin impersonation** — `POST /api/admin/impersonate/start` stores `impersonate_profile_id` in the session. While set, `tenancy.py`'s `current_profile_id` (via the `_impersonated_profile_id` helper) re-verifies the caller is still an admin on every request, then returns the impersonated profile's ID — so all tenant-scoped DB reads transparently re-point to that user. `ImpersonationReadOnlyMiddleware` (`web/middleware_impersonation.py`) blocks all unsafe HTTP methods (POST/PUT/PATCH/DELETE) with 403 `impersonation_read_only` while a session holds `impersonate_profile_id`, with an allowlist for `POST /api/admin/impersonate/stop` and `POST /auth/logout`. The middleware is registered **inside** `SessionMiddleware` in `main.py` so `scope["session"]` is available. Admin endpoints in `routers/admin.py` use a `require_real_admin` dependency that authorizes against `session["account_id"]` directly (bypassing the impersonated profile) so they remain admin-gated while impersonating. `POST /api/admin/impersonate/stop` clears the session key. `GET /api/me` returns `impersonating: {profile_id, email}` when active, `null` otherwise.
  - **Prod requirements:** `SESSION_SECRET` (the app **refuses to boot** in production if unset or left as the dev default — see `_session_secret()` in `main.py`), `GOOGLE_/GITHUB_CLIENT_ID/SECRET`, `ALLOWED_EMAILS`, `ADMIN_EMAILS`. Uvicorn must run with `--proxy-headers --forwarded-allow-ips="*"` (in the Dockerfile CMD) so Railway's `X-Forwarded-Proto: https` is trusted and `request.url_for()` builds **https** OAuth callback URLs — otherwise providers reject `http://` callbacks as `redirect_uri_mismatch`.
- **Score/generate are in `core/job.py`** — `routers/jobs.py` resolves the LLM client, prompt content, and template paths, then delegates to `job.score()`, `job.generate_resume_md/pdf()`, `job.generate_cover_md/pdf()`.
- **Generation is synchronous** — resume/cover generation blocks the request 30–60s while Claude + pandoc run. Acceptable for single-user local use.
- **SSE for real-time updates** — `sse.py` broadcasts job state changes; `App.jsx` subscribes via `EventSource`.
- **`llm_status.py`** tracks in-progress LLM calls (start/finish) so the UI can show spinners without polling.
- **Structured document editing (Phase 3b)** — `GET /api/jobs/{job_key}/{doc_type}/document` returns the stored structured JSON; `PUT` validates the body against a Pydantic `ResumeDocument`/`CoverDocument`, upserts the `Document` row, re-assembles the `.md`, and re-renders the PDF. Errors: `400` invalid `doc_type` or validation failure, `404` missing job or document, `500` render failure after the document was persisted. The old raw-Markdown editor bridge (`PUT .../markdown` and helpers `_put_document_markdown_sync` / `_read_body_text`) was retired.
- **Parse-on-read backfill (not persisted).** When `GET .../document` finds no `documents` row, it reconstructs the document from the on-disk `.md` (`core/document_parser`) and returns it **without persisting** — the `.md` stays authoritative and parser improvements always apply. A row is created only by a write: `PUT .../document` (edit) or a feedback refine. `POST .../feedback` must mutate+re-persist a structured doc, so it calls `_ensure_document_row` to backfill **and persist** a row from the `.md` first; it `404`s only when there's neither a row nor a `.md`.
- **Per-turn refinement snapshots** are written as structured JSON `{job_key}_{doc_type}_turn_{n}.json` in `generator/outputs/`. `GET /api/jobs/{job_key}/{doc_type}/turn/{n}/markdown` assembles Markdown on the fly from that JSON (`422` on schema mismatch).
- **Credits & Metering (sub-project 2 — DONE)** — `routers/credits.py`: `GET /api/credits` returns the caller's `{balance, rate, recent[]}` (last 20 ledger rows; `{balance:0, rate:0.0, recent:[]}` if no `Account` row). `require_admin` (a FastAPI dependency) resolves the account for `current_profile_id` and 403s unless `is_admin`; gates `POST /api/admin/credits/grant` (target by `profile_id` or `email`, `reason="admin_grant"` — the same `grant_credits` call a future Stripe webhook will reuse) and `GET /api/admin/system-balance` (reads the platform OpenRouter key's remaining balance via `LLM_API_KEY`, 502 on upstream failure, 503 if unset). `core.credits.InsufficientCredits` is registered in `web/main.py` as an exception handler returning **HTTP 402** `{error:"insufficient_credits", balance, floor}` — raised by `meter_action` (see `core/CONTEXT.md` → "Credits & Metering") when an account's balance is below `CREDIT_FLOOR`.
  - **Metered endpoints**: `POST /{job_key}/score`, `POST /{job_key}/generate/resume`, `POST /{job_key}/generate/cover` (`routers/jobs.py`); the intake-pipeline score/eval/refine steps (`intake_pipeline.py`); and `_do_extract_description` (extraction — gated but its debit is always 0, see `core/CONTEXT.md` limitation). All wrap the LLM call in `meter_action(db, profile_id, action=..., job_key=...)`.
  - Frontend: `CreditBalance.jsx` (navbar + User tab) shows balance/rate; a global 402 interceptor shows an "out of credits" toast and the navbar refetches. Admin-only system-balance panel reads `/api/admin/system-balance`. Known caveat: the balance does **not** auto-refresh after a successful metered action (those are SSE-driven, not request/response) — it can lag until the next load or a 402.
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
| `PATCH` | `/api/jobs/{job_key}/state` | State transition |
| `POST` | `/api/jobs/{job_key}/score` | Score job via LLM |
| `POST` | `/api/jobs/{job_key}/generate/resume` | Generate resume MD + PDF |
| `POST` | `/api/jobs/{job_key}/generate/cover` | Generate cover letter MD + PDF |
| `GET` | `/api/jobs/{job_key}/resume` | Serve resume PDF |
| `GET` | `/api/jobs/{job_key}/cover` | Serve cover letter PDF |
| `GET` | `/api/jobs/{job_key}/{doc_type}/document` | Return the stored structured document JSON (`ResumeDocument`/`CoverDocument`); if the `documents` row is missing, reconstructs it on the fly from the on-disk `.md` (via `core/document_parser`) **without persisting**, else `404` |
| `PUT` | `/api/jobs/{job_key}/{doc_type}/document` | Upsert an edited structured document; re-assembles `.md` + re-renders PDF |
| `POST` | `/api/jobs/{job_key}/{doc_type}/feedback` | Accept user section/item feedback (`{notes:[{section,label,note}]}`); ensures a `documents` row exists, backfilling+persisting from the `.md` if needed (`_ensure_document_row`); `404` if no row and no `.md`; drops empty notes (`400` if none); spawns `run_user_feedback_refine` background job (reuses refine path, eval-for-score, no restore-best, résumés trigger ATS gate); appends a Refinement-History turn tagged `source="user_feedback"`; returns 202 + job |
| `POST` | `/api/scraper/stage-job` | Ingest job from browser extension or scraper |
| `POST` | `/api/scraper/run` | Trigger background run of enabled API scrapers |
| `GET` | `/api/stats` | Pipeline activity bars + by-state counts (window param) |
| `GET` | `/api/skill-frequency` | Combined required+preferred skill counts (`skills`) plus `tech_stack`, distinct jobs, across all extracted jobs; no window. Also returns `profile_skills` (active user's skills, normalized) so the UI can flag covered skills. The job aggregation is cached in-process keyed by extracted-job count with a 60s TTL — a re-extraction that doesn't change the count can be up to 60s stale; tests reset `stats._SKILL_CACHE` via an autouse fixture. |
| `GET` | `/api/skill-frequency/jobs` | Job keys whose extraction data lists a given `skill` (normalized, any field) |
| `GET` | `/api/skills/aliases` | All alias groups `[{canonical, members}]` |
| `GET` | `/api/skills/aliases/search` | Canonicals matching `q` (substring over canonical + members) |
| `POST` | `/api/skills/aliases/assign` | Add/move `skill` into a group `canonical` (creates group if new) |
| `DELETE` | `/api/skills/aliases/member` | Remove `skill` from its group (`400` if it's the canonical self-row) |
| `POST/DELETE` | `/api/skills/profile` | Add/remove `skill` on the active profile (case-insensitive dedup) |
| `POST` | `/api/skills/owned` | Given `{skills:[…]}`, return the subset the active profile owns (alias + case aware); echoes input strings |
| `GET` | `/api/session-cost` | Cumulative LLM token cost for current session |
| `GET` | `/api/credits` | Caller's `{balance, rate, recent[]}` (last 20 ledger rows) |
| `POST` | `/api/admin/credits/grant` | Admin-only; grant credits to a profile by `profile_id` or `email`, reason `admin_grant` |
| `POST` | `/api/admin/credits/tier` | Admin-only; set a profile's pricing tier (target by `profile_id` or `email`; validated against `payments.tier_margins()`) |
| `GET` | `/api/admin/system-balance` | Admin-only; remaining balance on the platform OpenRouter key |
| `POST` | `/api/admin/invite` | Admin-only; normalizes email, idempotently inserts `allowed_email` row, sends invite email via `core.email.send_invite` |
| `GET` | `/api/admin/invites` | Admin-only; list all invited emails |
| `GET` | `/api/admin/users` | Admin-only; list all users `[{profile_id, email, tier, credits, is_admin}]` |
| `GET` | `/api/admin/users/{profile_id}/purchases` | Admin-only; purchase history for a specific user; 404 if profile unknown |
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

## Known Issues

- `_serialize()` in `jobs.py` calls `Path.exists()` twice per job (resume_md_exists, cover_md_exists) on every `GET /api/jobs`. At current scale (<100 jobs) this is negligible. If job count grows, move to a per-job detail endpoint.
- Salary sort is lexicographic for non-numeric salary strings (e.g. "$120k–$150k"). Values without parseable numbers sort as 0.
