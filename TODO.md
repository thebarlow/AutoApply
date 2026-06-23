# TODO

Backlog for multi-session work. Update this file whenever scope changes or an item is completed:
mark items `[x]`, move them to **Done**, or revise scope notes inline.

## Bugs

- [ ] **Indeed job descriptions are not fully captured by the scraper.** The browser
  extension's Indeed content script (`browser-extension/content/indeed.js`) returns a
  truncated/partial description for at least some Indeed job layouts. Audit
  `getDescription`/`detailReadySelector` against current Indeed DOM and capture the full
  description body.

- [x] **Invite email times out to Zoho SMTP.** Fixed: replaced raw Zoho SMTP
  (`smtp.zoho.com:465`, blocked/throttled by Railway egress) with the Resend HTTP API
  in `core/email.py`. Now needs `RESEND_API_KEY` (+ optional `RESEND_FROM`) env vars;
  `ZOHO_SMTP_*` removed. Sends from a Resend-verified domain (matthewbarlow.me).

- [ ] **Improve invite-email deliverability (lands in spam).** Resend sends work but
  Gmail files them as spam. To fix, in order of impact:
  1. **Add a DMARC record** (Resend sets SPF+DKIM on verification but not DMARC). TXT at
     `_dmarc.matthewbarlow.me` = `v=DMARC1; p=none; rua=mailto:dmarc@matthewbarlow.me;`.
     Start `p=none` (monitor), tighten to `p=quarantine` after SPF/DKIM align cleanly.
  2. Confirm SPF + DKIM show green/verified in the Resend dashboard.
  3. **Switch to a sending subdomain** to isolate reputation from the root domain: verify
     `send.matthewbarlow.me` in Resend and set `RESEND_FROM=Auto Apply <noreply@send.matthewbarlow.me>`.
  4. Have early recipients mark "Not spam" — positive engagement signal during warm-up.

- [ ] **`config` table is global, not tenant-scoped (multi-tenant settings bleak).**
  `Config` is a pure key-value store (PK = `key` only), so per-user settings stored there
  are shared across all tenants and any user can change them for everyone. Found during the
  profile/prompt tenancy audit (the per-profile resume/prompt endpoints were fixed in
  `[fix] Scope profile/prompt/setup endpoints to tenancy seam`; this is the remaining gap).
  Affected keys, by priority:
  1. **Scoring weights / thresholds** (`w1`, `w2`, `auto_reject_threshold`,
     `auto_approve_threshold`) — read in `web/routers/jobs.py:_load_weights` and applied to
     **every tenant's** scoring/intake. Live correctness bug (shared tuning), not a data leak.
  2. Scraper prefs (`source_remotive`/`source_remoteok`, `keywords_whitelist/blacklist`,
     `max_jobs_per_source`, `job_searches`) — shared, but the API scrapers are dormant.
  3. LLM provider config + LaTeX templates (`llm_providers`, `named_providers`,
     `latex_templates`, …) — arguably platform-global/admin-only now that the platform owns
     the LLM key in hosted mode; decide global-admin vs per-tenant rather than auto-scope.
  Fix is a schema change (add `profile_id` to the `config` PK + Alembic migration) and a
  tenant-aware `_get`/`_set` across ~15 endpoints — run it through the spec workflow as its
  own task, not a hotfix. Until then, scoring-weight edits in hosted mode are global.

- [ ] **`PUT /api/config/profiles/active` is a dead/legacy multi-profile switcher in hosted
  mode.** It writes the global `dev_tenant_id` Config row, which production's
  `current_profile_id` ignores (1 account = 1 profile via the session seam). Harmless but
  confusing and lets a user clobber the shared dev-stub row. Remove the endpoint (and the
  frontend profile switcher) in hosted mode, or gate it to dev/admin-only. Verify no
  React caller depends on it before deleting.

## Features

- **Profile Schema Engine (user-defined résumé sections).** Replace the hardcoded 5-section
  résumé model with a user-definable recursive tree. Decomposed into 5 sub-projects, each
  with its own spec → plan → impl cycle. **RELEASE CONSTRAINT: each sub-project merges to
  LOCAL `main` only — do NOT push `main` until the whole swap (#1–#5) is complete.**
  - [x] **#1 Schema engine** — recursive closed-vocabulary tree (`core/profile_tree.py`) as
    profile source of truth; `legacy_to_tree`/`tree_to_legacy`. DONE (local main).
  - [x] **#2 Builder UI** — React tree editor (`react-dashboard/src/components/widgets/profile-tree/`):
    render/rename/reorder/add/remove sections + fields, section gallery, lock/visibility.
    DONE (local main; phased 2A/2B/2C).
  - [x] **#3 Schema-driven LLM generation + section/item prompts** — `core/section_generator.py`
    Model 2 (per-section gen); `build_section_prompt` folded prompts; node-id `{profile:<id>}`
    /`{job.}` context tokens; `PromptEditorModal` two-column pill editor w/ draggable context
    folders; visibility-aware `tree_to_legacy`. Dev-only compare harness
    (`POST /api/dev/resume-compare/{job_key}`). DONE (local main, 2026-06-22).
  - [ ] **#4 Schema-driven RENDERING of custom sections — IN PROGRESS (full tree swap).**
    Spec `docs/superpowers/specs/2026-06-22-schema-driven-document-rendering-design.md`.
    Retires the typed `ResumeDocument` résumé pipeline; the **document tree** (profile tree
    snapshot w/ authored values baked in, invisible/`context_only` nodes pruned) becomes the
    résumé source of truth in `documents.structured_json` under a `schema:"tree-v1"`
    discriminator (legacy rows render via the old assembler — no data migration). Cover letter
    stays typed. **Frontmatter retired:** contact + education are no longer protected via a YAML
    data channel (the LLM never authors them anyway — they aren't `llm_output` fields), so they
    render as ordinary tree sections via default templates; presentation is template-driven, not
    frontmatter-driven. Phased into FOUR (the generation switch cascades into the refine loop, so
    the pure engine is isolated from the risky wiring); each phase = own plan → subagent impl,
    merged to LOCAL `main`:
    - [x] **4A — Pure foundation — DONE (local main `1415846`, not pushed).** `core/document_tree.py`
      (`build_resume_document_tree` — prune invisible + `context_only`, bake authored, carry locked
      verbatim) + `core/tree_assembler.py` (`assemble_resume_tree_markdown` — role→formatter dispatch,
      preset + generic, tree order, no frontmatter); dev harness repointed to dogfood. 23/23 tests,
      final review clean. No production wiring. Plan: `docs/superpowers/plans/2026-06-22-schema-rendering-4a-foundation.md`.
    - **4B — Wire tree-v1 into production (headline win).** Split into 4B-1 (done) + 4B-2 (next).
      - [x] **4B-1 — Tree-v1 in production — DONE (local main `a83bc39`, not pushed).**
        `generate_resume_md` → `section_generator` → document tree → store `schema:"tree-v1"`
        (`core/resume_document_io.py`). `write_resume_markdown`/`_render_meta`/refine/`_restore_best`/
        turn-snapshot/`run_ats_check` all branch on the discriminator; legacy `ResumeDocument` rows
        render byte-for-byte unchanged. Frontmatter retired for tree-v1 (contact `# name` + ordered
        contact line + education render from body markdown; `_render_meta`→{} so `render_pdf` education
        injection no-ops; `generator/resume.css` `.resume > h1` rules, legacy `.resume-header h1`
        untouched). `core/ats_tree_adapter.py` projects tree→minimal `ResumeDocument` for the gate.
        Interim refine re-authors all `llm_output` sections via `build_resume_prompt`+`{job.extracted_description}`.
        Custom sections now appear on generated résumés. (Spec/plan: `docs/superpowers/{specs,plans}/2026-06-22-*4b*`.)
        Carry-forwards: remove orphaned `core/tree_render.py` (still imported by `tests/core/test_tree_render.py`);
        pull duplicated test fixtures into conftest.
      - [ ] **4B-2 — Per-section refinement engine.** Replace the interim whole-doc re-author: one eval
        LLM call returns a per-section breakdown (`{section: {score, issues}}`); regenerate only
        sub-threshold sections. Own spec → plan.
    - [ ] **4C — ATS gate rework.** Drop the required-fixed-heading hard-block + literal heading
      matching from `check_mechanical`; keep contact-at-top / text-layer / glyph-junk / per-job
      `ext_required_skills`-survive checks + the semantic LLM roundtrip. No roles, no synonym map
      (vendor synonym dicts are proprietary; no section is universally required — freshers/
      career-changers lack work history).
    - [ ] **4D — DocumentModal generic rebuild + feedback-on-tree.** Rebuild
      `react-dashboard/src/components/widgets/document/` to render/edit the document tree
      generically (reuse `profile-tree/` patterns); retarget `POST /{doc_type}/feedback` refine
      to tree nodes. Largest, mostly frontend. Cover editing unchanged.
- [ ] **Profile Schema Engine #6 — User-formatted PDF + live preview (NEW; sequenced #4 → #6 → #5).**
  Live in-dashboard PDF render + a constrained, user-customizable template system: the user
  controls how each section/item renders (templates), with ATS-safety enforced by the templates
  themselves. Depends on #4 (not #5); the 4D DocumentModal is its UI home. Own spec when reached.
  - [ ] **#5 Onboarding parse** — map novel/uploaded résumé sections onto the schema during
    first-run onboarding. After #6.

- [ ] **High-effort toggle.** A toggle (per-prompt and/or a general switch) that swaps to a
  more capable model for a request, consuming more credits in exchange for higher quality.
  Surface the cost implication in the UI.

- [ ] **Feedback tab → admin ticketing.** Add a Feedback link in the navbar where users
  submit suggestions. Submissions become tickets visible in the Admin tab. A ticket has a
  sender, title, and description; admins can mark tickets completed and add notes. Keep it
  simple but robust enough to ingest user feedback and iterate. (New `tickets` table; user
  submit endpoint + admin list/update endpoints; navbar entry + admin panel.)

- [ ] **Auto-score jobs after upload.** Trigger scoring automatically once a job is ingested
  (extension stage-job + manual upload), instead of requiring a manual score action.

- [ ] **Remove "For Developers" from help docs.** Hosted users interact via the website,
  not a repo checkout; drop `Obsidian/Auto Apply/Docs/For Developers.md`.

- [ ] **Flesh out "Making a Good Master Resume" help doc.** Add concrete tips for writing a
  strong master résumé (`Obsidian/Auto Apply/Docs/Making a Good Master Resume.md`).

### Hosting / SaaS conversion

The SaaS conversion is split into sequenced sub-projects, each with its own spec → plan → impl
cycle. Foundation done; building up the stack: **Auth ✅ → Credits ✅ → Payments ✅ → Onboarding**.

- [x] **Multi-tenancy rework** — DONE (Phases 1–3 merged to main, 2026-06-10/11). SQLite → Postgres
  + Alembic; `profile_id` on `jobs`/`documents`/`skill_aliases`; `current_profile_id` seam +
  `scoped()` + `before_flush` tenant guard; platform-owned LLM key (env). See **Done** section and
  `docs/superpowers/specs/2026-06-10-multi-tenancy-rework-design.md`.

- [x] **Hosting (PaaS)** — DONE (2026-06-11). Live at `https://autoapply.matthewbarlow.me` on
  Railway (Dockerfile build, managed Postgres, `/data` volume, alembic-on-startup). Currently gated
  by a single-user HTTP Basic password (`BASIC_AUTH_*`) — replaced by real auth below. Tray app +
  browser extension stay local (not wired to the hosted API). See `ARCHITECTURE.md` → Deployment.

- [ ] **(1) Auth & Identity** — SPEC + PLAN WRITTEN, not yet executed.
  `docs/superpowers/specs/2026-06-11-auth-identity-design.md` +
  `docs/superpowers/plans/2026-06-11-auth-identity.md`. **Decision: self-hosted Authlib (Google +
  GitHub OAuth) + Starlette signed-cookie sessions, NOT a managed provider** (Clerk/Auth0 was the
  earlier idea — rejected to avoid the dependency/cost for a dashboard-only app). `account` +
  `identity` tables (1 account = 1 profile, link-by-verified-email); swaps the `current_profile_id`
  seam to read the session in prod; pure-ASGI gate on `/api/*` replaces the Basic gate; email-allowlist
  beta (`ALLOWED_EMAILS`); `ADMIN_EMAILS` bypass + first admin claims `profile_id=1`. **Gates 2–4.**

- [ ] **(4) Onboarding UX rework** — needs its own brainstorm/spec. Drop the API-key step (platform
  owns the key now); surface credit balance + buy flow; gate features on credits. **Also must solve
  the job-ingestion gap:** with the browser extension unhooked from the hosted API, hosted users
  currently have NO way to get jobs in — needs a manual add/paste path (or hosted scraping). Auth,
  Credits, and Payments are all done — this is the last remaining dependency.

- [ ] **Make landing page.** A public marketing page whose purpose is to **sell the product**.
  Must be viewable whether or not the user is signed in. Explain what AutoApply is, who it's for, and
  what it does (scrape → tailor résumé/cover → apply), with a clear call-to-action (sign in / get
  started / buy credits). Non-whitelisted/logged-out visitors currently hit the auth gate or an empty
  app with no explanation — the landing page replaces that with a real pitch. Dashboard stays behind
  auth; the landing page renders in front of it for everyone.

- [ ] **Improve the document feedback system.**
  _Current system:_ In `DocumentModal`, the user attaches free-text notes to individual items
  (profile/experience/education/project/skills) or to whole sections, plus a cover-letter feedback
  box. Submitting batches the notes to `POST /{doc_type}/feedback`; each note becomes a
  `{category:"user_feedback", description:"<label>: <note>"}` issue (`build_feedback_issues`) and is
  fed to the **existing refine prompt** as a one-shot `run_user_feedback_refine` (refine → eval-for-score,
  no restore-best; résumés trigger the ATS gate). It reuses the auto-refine machinery wholesale — there
  is no feedback-specific prompt, no preview/diff of the proposed change, no per-note accept/reject, and
  no conversation/history of prior feedback.
  _Possible improvements:_ a dedicated feedback-refine prompt that's better at localized edits; show a
  diff/preview before committing; per-note apply/skip; multi-turn feedback (let the user iterate without
  re-opening); surface which notes the model actually addressed; and richer anchors than a text label
  (the LLM currently locates the target only from the `label` string).

- [ ] **Persistent user memory** — Store durable user directives, e.g. "Never say this",
  "This project is my best portfolio piece". Referenced by the LLM during generation.

- [ ] **User skill interview** — Combines job analysis + persistent memory. Interview the user on
  comfort level with specific techs; confidence tier governs how the LLM references them
  (omit low-confidence, slight upsell on mid-confidence, full claim on high-confidence).

- [ ] **Nicer process/skill formatting** — Format process descriptions with more tables, fewer
  bullet points, less prose. Condense phrasing:
  "Strong proficiency in Python" → "Python",
  "Hands-on experience with LLMs and generative AI" → "LLMs, generative AI".

## Done

- [x] **(3) Payments** — DONE (2026-06-13). Stripe Checkout for credit-pack purchases:
  `core/payments.py` (`load_packs`/`credits_for_price`, parses `STRIPE_PACKS` JSON env map,
  price_id -> credits) + `core/stripe_client.py` (thin wrapper over `stripe` SDK v15.2.1 —
  `create_customer`, `create_checkout_session`, `retrieve_price`, `construct_event`). New
  `purchase` table (Alembic `aa01payments01`: profile_id, stripe_session_id [unique],
  stripe_event_id [unique, idempotency key], price_id, credits, amount_usd, status
  pending|completed, created_at) + `account.stripe_customer_id`. `web/routers/payments.py`
  (`/api/payments/*`): `GET /packs`, `POST /checkout` (auth-gated, creates Stripe customer on
  first buy, records a pending `Purchase`, returns the Checkout URL), `POST /webhook`
  (signature-verified, idempotent on `stripe_event_id`, marks the purchase completed and grants
  credits via `grant_credits(reason="purchase")`), `GET /history`. `web/auth/middleware.py` adds
  `/api/payments/webhook` to `_EXEMPT_PATHS` so the unauthenticated Stripe callback bypasses the
  prod auth gate (secured by signature instead). Pricing rule: 1000 credits = $1; default packs
  $5/5000, $15/15000, $40/40000. Frontend: `api.js` (`getPacks`/`getPurchaseHistory`/
  `startCheckout`), `BuyCreditsModal.jsx`, navbar `+` buy button + click-to-see "session usage in
  credits" overlay (replaced "Session Cost: $X", reads `window.__creditRate` set by
  `CreditBalance.jsx`), purchase-success toast + balance refresh, purchase history in
  `UserHome.jsx`. New env vars: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PACKS`,
  `APP_BASE_URL`. Known limitation: refunds are admin-manual only — no automatic credit clawback.
  See `ARCHITECTURE.md` → "Payments", `core/CONTEXT.md`, `web/CONTEXT.md`. **Unblocks (4) Onboarding.**

- [x] **(3+) Tiered credit pricing** — DONE (2026-06-15). Layered on top of (3) Payments. Moved
  margin from consumption to the *purchase* side: `account.credit_rate` now defaults to 1.0 for
  metered users (was 1.5), so features cost the same credits for everyone while the same dollar
  amount buys different credits per tier. New `account.tier`/`purchase.tier` (`beta`/`friends_family`/
  `standard`; Alembic `aa02tiers01` backfills existing accounts to `beta` and resets `credit_rate`
  1.5→1.0; new signups → `standard`). `core/payments.py` rewritten as a pure pricing calculator
  (per-tier margins, bulk discounts, fee model, profit guard, round-to-25); `STRIPE_PACKS` retired
  for `STRIPE_PRICE_IDS` + the calculator. Tier-filtered `GET /packs` and tier-aware `POST /checkout`
  (server-computed credits); admin `POST /api/admin/credits/tier`. `BuyCreditsModal.jsx` shows a bonus
  badge on discounted packs. Spec/plan: `docs/superpowers/{specs,plans}/2026-06-15-tiered-credit-pricing*`.

- [x] **(2) Credits & Metering** — DONE (2026-06-12). Cost-backed credit ledger
  (`credit_ledger`, append-only source of truth) + cached `account.credit_balance`/`credit_rate`
  (Alembic `85e2c6aab4f8`). `core/metering.meter_action` gates score/generate/eval/refine/extract on
  the tenant's balance (`InsufficientCredits` → HTTP 402), meters real LLM cost via `call_llm` →
  `record_call`, and settles one debit row per action; `core/credits.to_credits` converts
  `raw_cost_usd * rate * 1000` (1000 credits = $1). New accounts get a signup grant
  (`CREDIT_SIGNUP_GRANT`, default 100); tiers (`credit_rate`): developer 0 (free), friends-and-family
  1.5 (default), standard 10.0 — set manually, no admin UI yet. `GET /api/credits` +
  `POST /api/admin/credits/grant` + `GET /api/admin/system-balance` (`web/routers/credits.py`);
  `CreditBalance.jsx` navbar/User-tab widget + global 402 "out of credits" toast. Known limitations:
  extraction's debit always settles to 0 (its LLM call bypasses `call_llm`, effectively free in v1);
  the navbar balance doesn't auto-refresh after a successful action (SSE-driven, lags until next
  load/402). See `ARCHITECTURE.md` → "Credits & Metering", `core/CONTEXT.md`, `web/CONTEXT.md`.
  **Unblocks (3) Payments.**

- [x] **Document modal polish + backfill correctness** — Parser now handles legacy LLM résumé
  markdown (experiences split on `### ` or bold-only headings; one-line `**Name:**` projects), fixing
  experiences/projects collapsing into a single item. `GET .../document` switched to **parse-on-read**
  (reconstruct from `.md` without persisting) so a lossy parse can't shadow the source; `POST .../feedback`
  backfills+persists a row first (`_ensure_document_row`) since the refine mutates it. Frontend: Enter-to-save
  + dirty-gated **Save** button in `ItemEditor` (Shift+Enter = newline), Edit/Feedback popover moved to the
  right of the item, **section-level feedback** on section titles, and capture-phase **Escape** handling
  (exits inline edit/feedback first, then closes the modal back to job details — no longer jumps to the User view).

- [x] **Interactive document modal** — The Resume/Cover toolbar's single pencil (✎) button (Edit/Expand
  removed) opens `DocumentModal`, backed by `widgets/document/` (`InteractiveResume`, `ResumeSection`,
  `items`, `ItemPopover`, `ItemEditor`, `CoverView`, `highlight.css`): hover-highlight per item, inline
  editing, and per-item/cover feedback → one-shot regenerate via `POST /{doc_type}/feedback`. Retired the
  `StructuredEditor` overlay. Also fixed `GET /{job_key}/{doc_type}/document` to backfill a missing
  `documents` row by reconstructing from the on-disk `.md` (`core/document_parser`) before returning 404.

- [x] **Settings → User tab application stats** — Rotating counter in `UserHome.jsx`: "You've
  applied to {x} jobs" with the verb+count highlighted/clickable, cycling Applied → Scraped →
  Resumes (`STAT_METRICS`). Today/Week/All-time control filters counts via new `totals` field on
  `GET /api/stats` (window-filtered by `applied_at`/`scraped_at`/`resume_generated_at`).

- [x] **Remove Activity chart** — Removed the scraped/resumes/covers bar chart from `UserHome.jsx`;
  dropped the orphaned `session` window from `/api/stats` (`_VALID_WINDOWS`, `get_session_start`).

- [x] **Description chip ownership styling** — Processed-description skill chips are colored by a
  3-state ownership check (`POST /api/skills/owned`, alias + case aware): green = a skill I have,
  amber = a *required* skill I lack (résumé gap), neutral = other. Also fixed the `SkillChipModal`
  "A skill I have" toggle (was never given `isOwned` / never refreshed, so it looked dead).

- [x] **Skill aliases + clickable chips** — Global `skill_aliases` table (arbitrary-size synonym
  groups, seeded from the curated `_ALIASES` map); case variants now merge automatically
  (`FASTAPI`/`FastAPI` → one entry). `SkillChipModal` (opened from In-Demand legend names, By-Skill
  bar labels, and job-description chips) assigns aliases, edits groups, and marks skills as owned.
  Backend: `web/routers/skills.py`, case-folded `core/skill_analytics.py`, alias-aware
  `web/routers/stats.py` with cache invalidation.

- [x] **"Ready" jobs vanished from Inbox and Archives** — `ready` was in neither `INBOX_STATES`
  nor `ARCHIVE_STATES` in `Pipeline.jsx`, so ready jobs matched no tab. Added `ready` to the
  Inbox (generated-but-not-applied jobs stay actionable).

- [x] **In-Demand Skills charts retained deleted-job skills** — `get_skill_frequency` and
  `/skill-frequency/jobs` in `web/routers/stats.py` didn't exclude soft-deleted jobs
  (`state == 'deleted'`). Added the exclusion to both queries; counts recompute live so existing
  data recounts automatically.

- [x] **LLM & document hardening — Phase 1: structured LLM parsing** — LLM responses for data tasks
  validate against Pydantic models via `core/schemas.py` `parse_llm_json` (`ScoreResponse`,
  `EvalResponse`, `ExtractionResponse`, `ParseResponse`). Replaced ad-hoc string parsing.

- [x] **LLM & document hardening — Phase 2: prompts in the DB** — Prompt templates moved from files
  into the `prompt_defaults` (factory) + `prompts` (per-profile) tables; `prompts/defaults/*.md` are
  seed-only. Runtime resolution via `User.resolve_prompt` with auto-repair; edited via
  `web/routers/prompts.py`. Legacy file prompts migrated by `migrate_file_prompts_to_db`.

- [x] **LLM & document hardening — Phase 3a: structured document generation** — Generation returns a
  JSON `ResumeGeneration` contract built into a typed `ResumeDocument`/`CoverDocument` and stored in
  the `documents` table; the `.md` is derived and PDFs render from it. Render metadata snapshotted at
  generation time. Résumé prompt reseeded via `resume_prompt_v2` gate.

- [x] **LLM & document hardening — Phase 3b: document as single source of truth** — `documents` row
  is authoritative; `.md`/PDF derived only via `write_resume_markdown`/`write_cover_markdown`.
  Retired raw-Markdown editing for a structured `GET/PUT .../document` API + React per-section form
  editor. Refine became a prose-only keyed patch (`apply_resume_patch`); per-turn snapshots are
  structured JSON with restore-best. Plus JSON-output hardening (`_llm_json_with_retry`: strict-JSON
  instruction + one corrective retry) to survive small models emitting invalid JSON.

- [x] **Job analysis: skill frequency** — Skill normalization + frequency aggregation across scraped
  jobs (`core/skill_analytics.py`), surfaced via `GET /api/skill-frequency` (+ `/jobs`) and the
  dashboard; flags skills covered by the active profile.

- [x] **One-page resume overflow** — Pearson resume ran ~0.5in past one page; refine/edit paths
  silently emitted 2-page PDFs (page check disabled). Added auto-shrink in `render_pdf` (steps the
  Playwright `page.pdf(scale=)` down to a 0.8 floor until it fits), tightened `resume.css` spacing,
  and re-enabled `max_pages=1` on the edit/refine paths.

- [x] **Document user feedback** — Expand modal (`DocumentModal.jsx`) shows the doc large
  side-by-side with a section-anchored feedback panel; submitting runs a one-shot refine via
  `POST /{doc_type}/feedback` → `run_user_feedback_refine` (reuses the refine path, eval-for-score,
  no restore-best).
