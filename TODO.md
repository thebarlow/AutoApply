# TODO

Backlog for multi-session work. Update this file whenever scope changes or an item is completed:
mark items `[x]`, move them to **Done**, or revise scope notes inline.

## Bugs

_(none)_

## Features

### Hosting / SaaS conversion

The SaaS conversion is split into sequenced sub-projects, each with its own spec → plan → impl
cycle. Foundation done; building up the stack: **Auth → Credits → Payments → Onboarding**.

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

- [ ] **(3) Payments** — needs its own brainstorm/spec. Stripe Checkout for credit-pack purchases +
  webhook → grant credits into the ledger (reuses `grant_credits`/the `admin_grant` code path). Now
  unblocked — Auth and Credits are both done.

- [ ] **(4) Onboarding UX rework** — needs its own brainstorm/spec. Drop the API-key step (platform
  owns the key now); surface credit balance + buy flow; gate features on credits. **Also must solve
  the job-ingestion gap:** with the browser extension unhooked from the hosted API, hosted users
  currently have NO way to get jobs in — needs a manual add/paste path (or hosted scraping). Depends
  on Auth + Credits + Payments.

- [ ] **Public landing / marketing page.** Non-whitelisted users currently hit the auth gate or an
  empty app with no explanation. Build a public (unauthenticated) landing page that explains what
  AutoApply is, who it's for, and what it does (scrape → tailor résumé/cover → apply), so visitors
  without access can understand the product even before they can use it. Include a clear call-to-action
  (sign in / request access) and set expectations about the invite-gated beta. Should render for
  logged-out users while the dashboard stays behind auth.

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
