# TODO

Backlog for multi-session work. Update this file whenever scope changes or an item is completed:
mark items `[x]`, move them to **Done**, or revise scope notes inline.

## Bugs

- [x] **Implement structured error logging — DONE (2026-07-12, v1).** Central
  `core/logging_config.py` (`setup_logging()`) installs a stdout handler + size-based
  `RotatingFileHandler` (5MB×5) on the root logger and a `threading.excepthook`/`sys.excepthook`;
  wired at `web/main.py` + `tray_app/main.py` startup; env-configurable via
  `LOG_LEVEL`/`LOG_DIR`/`LOG_FILE`; `logs/` gitignored. Failure-path prints in the intake
  pipeline, `core/job.py`, and scrapers now use `logger.exception` (full tracebacks in the file).
  `job.last_result_error` unchanged (still the short user-facing message). **Deferred v2:**
  queryable DB error table + dashboard error viewer. Spec/plan in
  `docs/superpowers/{specs,plans}/2026-07-12-structured-error-logging*`.
  Original ask: persistent, queryable error logging so failures (esp. background
  intake/pipeline threads) are captured and surfaced — goal: stop hand-copying terminal output.
  Observed 2026-07-10 (motivating examples, both in the intake pipeline `_run` thread,
  `core/job.py`) — **both root causes also FIXED (2026-07-12)**:
  1. **LLM extraction returns empty with `finish_reason='length'`** — FIXED. `extract_description`
     now starts at `max_tokens=4096` and retries once with a doubled budget on truncation, then
     raises a clear "truncated or empty after retry" error instead of a bare empty-response error.
  2. **`sqlite3.OperationalError: database is locked`** — FIXED. `db/database.py` now sets
     `PRAGMA journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout=10000` on every SQLite
     connect (via a `connect` event listener, SQLite-only). WAL lets readers proceed during a
     write and the busy timeout makes a contending writer wait instead of raising. Postgres in
     prod was already unaffected.

- [x] **Indeed job descriptions not captured by the scraper — FIXED** (2026-07-09). Root cause
  (confirmed live via Claude-in-Chrome, not truncation): Indeed migrated the detail pane to
  `div.react-native-html-content.simple-job-description-html` and dropped the legacy
  `#jobDescriptionText` id, so `getDescription()` returned `""` and `detailReadySelector` never
  fired. `indeed.js` now uses a fallback selector chain (`_DESCRIPTION_SELECTORS`) for both, keeping
  `innerText` to strip Indeed's embedded `<style>` block. Verified full body captured on two live jobs.
  See `browser-extension/CONTEXT.md` → Resolved.

- [x] **Invite email times out to Zoho SMTP.** Fixed: replaced raw Zoho SMTP
  (`smtp.zoho.com:465`, blocked/throttled by Railway egress) with the Resend HTTP API
  in `core/email.py`. Now needs `RESEND_API_KEY` (+ optional `RESEND_FROM`) env vars;
  `ZOHO_SMTP_*` removed. Sends from a Resend-verified domain (matthewbarlow.me).

- [x] **Improve invite-email deliverability (lands in spam).** Fixed (auth records live):
  1. DMARC published at `_dmarc.matthewbarlow.me` (`p=none`, Cloudflare DMARC Management
     `rua`). Tighten to `p=quarantine` after a week of clean reports.
  2. SPF + DKIM verified in Resend. DKIM (`resend._domainkey`) signs `d=matthewbarlow.me`
     → aligns with the From domain, so DMARC passes via DKIM; Resend routes Return-Path
     through `send.matthewbarlow.me` (amazonses) so SPF passes on the bounce domain.
  3. Sending-subdomain switch **not needed** — DKIM already aligns on the root domain, so
     `RESEND_FROM=@matthewbarlow.me` is fine.
  4. Remaining is warm-up only: early recipients mark "Not spam" / reply for engagement.

- [ ] **Follow-ups for email deliverability (non-blocking).**
  1. **Verify auth in practice:** send a real invite to Gmail → "Show original" → confirm
     SPF/DKIM/DMARC all say PASS. Beats the Cloudflare dashboard widget (report-driven,
     24–72h lag; empty/stale until traffic flows).
  2. **Tighten DMARC to `p=quarantine`** after ~a week of clean aggregate reports.
  3. Ignore Cloudflare's "BIMI in use — fail" — BIMI is optional (needs `p=quarantine`+
     often a paid VMC cert); irrelevant to spam placement.

- [x] **`config` table is global, not tenant-scoped (multi-tenant settings bleak). DONE** —
  per-tenant keys (scoring weights/thresholds, scraper prefs, contact links, template paths)
  now live in a new `profile_config` table (tenant-guarded, backfilled for every profile via
  Alembic `aa08profcfg01`); `web/routers/config.py` exposes `_get`/`_set` (per-tenant) and
  `_get_global`/`_set_global` (unchanged global `config` table for `dev_tenant_id`, migration
  gates, `named_providers`/`llm_*`, `latex_templates`, legacy prompt-picker keys). See
  `docs/superpowers/specs/2026-07-08-config-table-tenancy-design.md` and
  `docs/superpowers/plans/2026-07-08-config-table-tenancy.md`.

- [x] **`PUT /api/config/profiles/active` dead/legacy multi-profile switcher — REMOVED**
  (2026-07-09). Endpoint + `ActiveProfileBody` deleted from `web/routers/config.py`; frontend
  `setActiveProfile` (api.js) and the dead `ensureProfileWithProvider` helper removed; the only
  live caller (onboarding `StepResume`) no longer needs it since `getProfiles` returns `active_id`
  straight from the `current_profile_id` seam. Stale mocks + backend endpoint tests dropped;
  CONTEXT.md updated. Backend + FE tests green.

## Features

- **Guided section-prompt authoring for users (from the prompt-polish work).** Once we've
  settled how to best structure section/item prompts (baseline-facts + tailoring direction;
  honesty rules re: seniority/titles and proof-words; per-project technology surfacing), give
  that structure to users instead of a blank textarea. Two options to explore:
  1. **Pre-formatted template** — when a user adds/edits a section or list item, pre-fill the
     prompt field with the agreed structure (labeled "Baseline facts", "What to emphasize",
     "Do NOT claim", etc.) for them to fill in.
  2. **Full GUI questionnaire** — a guided form that asks plain questions ("What exactly did
     you do?", "What were your responsibilities?", "What technologies did you use?", "What
     should we NOT claim about this role?") and compiles the answers into a well-formed
     section/item prompt. Lowers the skill floor and enforces the honesty structure by design.
  Reference the live profile-9 section/item prompts as the worked example of the target format.

- **Pin / promote a generated value as the field's default, and use default text as a
  generation baseline.** Two related gaps in the section-generation model:
  1. **Promote-to-default:** when a user likes a particular LLM output for an item field
     (e.g. an Experience summary or Project description), give them a way to save it back as
     the field's stored `value` — optionally flipping the field to non-LLM-output so it then
     renders verbatim and is no longer regenerated. No such "pin this generation" action
     exists today.
  2. **Default-as-baseline:** an LLM-output field's current stored `value` is NOT shown to the
     generator (only the item/section `prompt` + non-output anchors are). Consider feeding the
     existing value in as an optional baseline ("improve on this, don't discard it") so a liked
     draft seeds the next generation instead of being ignored/overwritten. Decide the semantics
     vs. the item `prompt` (which currently carries the baseline facts).
  Note for context: today, marking an item field non-LLM-output renders its stored value
  verbatim; marking it LLM-output overwrites it and ignores the prior value.

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
      - [x] **4B-2 — Per-section refinement engine — DONE (local main `ba2ce57`, not pushed).**
        Spec/plan `docs/superpowers/{specs,plans}/2026-06-23-*4b2*`; 6 TDD tasks subagent-driven,
        final opus review READY TO MERGE (no Critical/Important); 75/75 on 4B-2+adjacent. `SectionEvalResponse`
        schema + `resume_eval_sectioned` prompt key; `Job.evaluate_resume_sections` scores only regenerable
        sections (unlocked `llm_output`) by name; `generate_resume_by_section` gained optional
        `only_sections`/`critiques` (behavior-preserving); `authored_values_from_tree` carries passing
        sections forward; `web/intake_pipeline._run_resume_section_refinement` loop (stop when all
        regenerable ≥ `resume_refine_pass_score` or max_turns; turn score = MIN; best-by-min restore)
        dispatched from `_run_doc_refinement` for tree-v1 résumés only. Cover/legacy whole-doc loop +
        `_refine_doc_md` untouched (feedback-refine → 4D). Carry-forwards: dispatch double-fetch (1-line);
        de-dup `_restore_best_sections` vs whole-doc `_restore_best` (note divergence first); test fixtures→conftest.
    - [x] **4C — ATS gate rework — DONE (local main `11a8794`, not pushed).**
      Spec/plan `docs/superpowers/{specs,plans}/2026-06-23-*4c*`; 2 TDD tasks subagent-driven,
      final opus review READY TO MERGE (no Critical/Important); 33/33 ATS+adjacent. Removed the
      `section_missing` critical hard-block and the skill synonym map (`_RAW_SYNONYMS`/`_SKILL_SYNONYMS`)
      from `core/ats_gate.check_mechanical` — `_present` is now literal-only. Kept text-layer / contact /
      glyph-junk / `present_skill_dropped` mechanical checks + the score formula + blocking contract
      (`AtsReport.build`, confirm-applied) unchanged. Section-structure verification moved to the
      advisory semantic roundtrip: new warning-only `roundtrip_sections` diff in `check_roundtrip`
      (document `section_order` vs LLM-parsed `sections`, suppressed on empty parse). `section_order`
      now feeds the roundtrip (consumer moved from mechanical → semantic); adapter docstring updated.
      Both tree-v1 and legacy `ResumeDocument` rows lose the section hard-block identically (intended).
    - [x] **4D — DocumentModal generic rebuild + feedback-on-tree** (merged to local main
      `06219ff`, 2026-06-24, not pushed). New generic `document/DocumentTree.jsx` + `docTreeOps.js`;
      retired legacy `InteractiveResume`/`ItemEditor`/`ItemPopover`/`ResumeSection`/`items.jsx`;
      `DocumentModal` rewired to the tree; `PUT /document` tree-v1 branch; node-anchored feedback
      routed through 4B-2 selective per-section regen for tree-v1 résumés. Bonus document-editor
      layout + page-limit folded into the same merge. Cover editing unchanged. **#4 complete.**
- [ ] **Profile Schema Engine #6 — User-formatted PDF + live preview (NEW; sequenced #4 → #6 → #5).**
  Live in-dashboard PDF render + a constrained, user-customizable template system: the user
  controls how each section/item renders (templates), with ATS-safety enforced by the templates
  themselves. Depends on #4 (not #5); the 4D DocumentModal is its UI home. Own spec when reached.
  - [x] **#6A — Live in-dashboard PDF preview** (merged to local main `405e51a`, 2026-06-25,
    not pushed; branch deleted). Spec/plan `docs/superpowers/{specs,plans}/2026-06-25-live-pdf-preview*`.
    Side-by-side editor + read-only real-PDF iframe in DocumentModal, refresh-on-save (cache-busting
    `?v=` version bump after a successful PUT, which already re-renders both PDFs), both résumé +
    cover, responsive stacking, not-generated placeholder. New `document/DocumentPreview.jsx`. Pure
    frontend, no backend changes. 136/136 frontend + build. Manual QA (non-edge-case paths) confirmed
    by user. Final opus review clean. Deferred Minor: narrow-breakpoint layout polish.
  - [x] **#6B — User-customizable templates** — 6B-1 (output formats) + 6B-2 (résumé themes) both done.
    - [x] **#6B-1 — Output formats** (merged to local main via `--no-ff`, 2026-06-26, not
      pushed; branch deleted). Per-LLM-field output format (Bullet list / Paragraph) on the
      profile tree, driving both the generation JSON shape ("# Output Format" prompt block +
      response coercion) and deterministic rendering; presets default experience→bullets,
      summary/projects→paragraph; idempotent backfill (`scripts/backfill_output_formats.py`,
      RAN on dev profile 9). Registry `core/output_formats.py`; `GET /api/output-formats` +
      profile-tree `<select>`. Tree-v1 only; legacy/cover untouched. Backend 878 + FE 138 green.
    - [x] **#6B-2 — Résumé themes** (merged to local main `5b4ef7f` via `--no-ff`, 2026-06-26,
      not pushed; branch deleted). Curated theme picker (classic/modern/compact), profile-level,
      résumé only, picked in profile editor, re-rendered on open when stale. `generator/themes.py`
      registry; `render_pdf(css_path=)` override; two standalone ATS-safe stylesheets (both tree-v1
      + legacy selector families); `User.resume_theme`; `jobs.resume_rendered_theme` col + migration
      `aa07themes01`; `serve_resume` best-effort re-theme-on-open; `GET /api/themes` + profile
      `<select>`. Classic byte-identical. Backend 904 + FE 140 green. Manual re-theme QA deferred to user.
  - [x] **#5 Onboarding parse** — schema-aware parse: open `extra_sections` in the parse schema;
    v2 `resume_parse` prompt + idempotent reseed for stock profiles; `core/parsed_sections.py`
    (build_section_from_parsed + add/replace/merge/find tree ops); two-phase API
    `POST …/parse/propose` (no persist) + `…/parse/apply` (per-section add/replace/merge/skip,
    caps→422, preserves file/LLM fields); `ParsePreview` React component; wired into onboarding
    `StepResume` and the Settings new-profile wizard. Backend 927 + FE 148 green; opus whole-branch
    review READY TO MERGE. **This is the LAST sub-project — the whole swap (#1–#5) is now complete.**
    - [ ] **Follow-up:** no UI triggers re-parse on an EXISTING populated profile (backend apply
      already supports it with add-only-safe skip defaults; only onboarding + new-profile wizard
      surface it). Add a re-parse button in the profile/settings UI when reached.

- [ ] **High-effort toggle.** A toggle (per-prompt and/or a general switch) that swaps to a
  more capable model for a request, consuming more credits in exchange for higher quality.
  Surface the cost implication in the UI.

- [ ] **Feedback tab → admin ticketing.** Add a Feedback link in the navbar where users
  submit suggestions. Submissions become tickets visible in the Admin tab. A ticket has a
  sender, title, and description; admins can mark tickets completed and add notes. Keep it
  simple but robust enough to ingest user feedback and iterate. (New `tickets` table; user
  submit endpoint + admin list/update endpoints; navbar entry + admin panel.)

- [x] **Auto-score jobs after upload** — ALREADY DONE (verified 2026-07-06). `POST /api/scraper/stage-job`
  (`web/routers/scraper.py`) fires `run_pipeline` in a background thread on every ingest — extension
  stage-job AND manual upload (`UploadModal` → `uploadJob` → same endpoint). `run_pipeline`
  (`web/intake_pipeline.py`) runs description extraction → scoring automatically; no manual score action.

- [x] **Remove "For Developers" from help docs — DONE** (2026-07-13). File already absent from
  `Obsidian/Auto Apply/Docs/`; no code references remained.

- [x] **Flesh out "Making a Good Master Resume" help doc — DONE** (2026-07-13). Replaced the
  "Coming Soon" stub with concrete guidance: be specific/quantify, name technologies explicitly,
  cover what-you-did/responsibilities/tech/outcome per item, include a superset of experience,
  honesty rules, and using score breakdowns to find profile gaps
  (`Obsidian/Auto Apply/Docs/Making a Good Master Resume.md`).

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

- [x] **(4) Onboarding UX rework** — **Guided tour DONE (2026-07-07):** reworked from the initial
  two-arc design into a single **action-gated** react-joyride walkthrough (`tourSteps.js` `TOUR_STEPS`:
  profile editor → sections/lock/visibility/prompt → job inbox → open demo job → score → generate →
  credits). Gated steps hide Next and wait on an `advanceOn` window event the user fires (`openEvent`
  opens the panel a step needs); `spotlightClicks` lets the user click the highlighted control through
  the overlay. `TourController` + `useOnboardingTour` state machine (`unstarted→part1_done→completed/
  skipped`); state persists via `PATCH /api/onboarding/tour` (`web/routers/onboarding.py`); "Take a
  tour" replay in navbar. **Demo job DONE (2026-07-07):** `core/demo_data.py` `seed_demo_job` inserts
  one pre-scored demo job at profile creation (idempotent by URL, best-effort) so the tour's score/open/
  generate steps have real content without an LLM call. **Job-ingestion DONE (2026-07-10):** all
  three hosted intake paths now work:
  1. **Manual add/paste** (verified 2026-07-06) — `UploadModal` (`Pipeline.jsx`) → `uploadJob` →
     `POST /api/scraper/stage-job` → `run_pipeline` (extract + score).
  2. **Browser extension → hosted API — DONE (verified live 2026-07-09).** The extension is wired
     to the hosted server: `service_worker.js` hardcodes `SERVER = https://autoapply.matthewbarlow.me`
     and POSTs `stage-job` with an OAuth bearer token (`popup.js` login flow, `manifest.json` host
     permission). LinkedIn/Indeed scrapes land on the live account. (Earlier TODO claim that it "still
     points at localhost" was stale.)
  3. **Find Jobs tab — DONE (2026-07-10).** Server-side, UI-triggered intake of remote boards:
     the Remotive/RemoteOK API scrapers (`scraper/search.py::search_sources`) run behind
     `POST /api/scraper/search` (preview candidates, no persist) and `POST /api/scraper/scrape-selected`
     (persist selected + run pipeline), driven from the new `FindJobs.jsx` navbar tab
     (`/find-jobs`). The old dormant `POST /api/scraper/run` + `scraper_sources` config gate
     were retired. Spec/plan: `docs/superpowers/{specs,plans}/2026-07-10-find-jobs*`.

- [x] **Make landing page** — DONE (2026-07-06). Public `/about` marketing page shown to logged-out
  visitors (all routes redirect there) and reachable via the navbar "About" link for logged-in users.
  Pure frontend `landing/` tree: `Hero` (headline + CTA), `HowItWorks` (scrape→tailor→apply),
  `Features` (4 cards), `SignInCard` (Google/GitHub OAuth or "Go to dashboard" + closed-beta message).
  `App.jsx` routing + `Navbar` link; orphaned `LoginScreen.jsx` (absorbed into `SignInCard`) deleted.
  165/165 FE tests green. Spec/plan: `docs/superpowers/{specs,plans}/2026-07-03-landing-page*`.

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

- [ ] **Full codebase audit (security + redundancy + improvements).** Now that the SaaS stack
  (auth, credits, payments, onboarding) and the profile-schema-engine swap are all in, do a
  structured pass over the whole codebase before the next feature push. Cover:
  - **Security holes** — tenant-scoping gaps (esp. the global `config` table bug above and
    `PUT /api/config/profiles/active`), auth-gate exemptions (`_EXEMPT_PATHS`), the Stripe webhook
    signature path, admin-only endpoint guards, impersonation, secret handling / env-key writes in
    prod, SSRF/injection surfaces in the scrapers and LLM I/O, and any endpoint trusting client-sent
    fields (e.g. `is_onboarding`, server-computed credit amounts).
  - **Redundant / dead features** — dormant API scrapers, the legacy multi-profile switcher, orphaned
    modules (`core/tree_render.py`), duplicated test fixtures, and any UI paths retired by the schema-engine
    rework that still have backend remnants.
  - **Improvements** — the known-limitation list (extraction cost not metered, navbar balance not
    auto-refreshing, refund clawback, invite-email deliverability), test coverage gaps, and error-handling
    consistency.
  Produce a written findings doc (`docs/` audit note) with severity-ranked items, then convert the
  actionable ones into their own TODO entries. Consider running it through the `security-review` /
  `code-review` skills per-area rather than one giant pass.
  **DONE 2026-07-13** — findings written to `docs/audit-2026-07-13.md` (S1–S5 security, R1–R4 dead
  code, I1–I4 improvements). Actionable items broken out as the TODO entries directly below.

- [x] **[audit P1] Scope-or-delete the global-config prompt surface (S1/R1).** **DONE 2026-07-13** —
  deleted the dead `/api/config/prompts/*` CRUD endpoints + helpers (`_get_prompts`/`_set_prompts`/
  `_sync_active_prompt`, `PromptBody`/`ActivePromptBody`) from `web/routers/config.py` and their tests.
  They stored prompt content/`latex_templates` in the global `Config` table (cross-tenant write) and had
  no runtime consumer — live generation reads per-tenant prompts from the `prompts` table. `named_providers`
  read helpers kept (local-mode setup-status probe only). Docs synced (`web/CONTEXT.md`).

- [x] **[audit P1] Meter `draft_section_prompt` (S2).** **DONE 2026-07-13** — wrapped the LLM call in
  `meter_action(db, profile_id, action="draft")`; `InsufficientCredits` re-raised to the global 402
  handler. Added regression test `test_draft_gated_on_insufficient_credits`.

- [x] **[audit P1, gated] Server-derive `is_onboarding` in `parse_apply` (S3).** **DONE 2026-07-15** —
  `parse_apply` now ignores the client flag entirely: onboarding is derived server-side as "no stored
  section holds data" (stricter than `parse_propose`'s builtin-only check — custom-section data also
  blocks the wipe). Regression test `test_forged_onboarding_flag_cannot_wipe_populated_tree` asserts a
  forged `is_onboarding=True` against a populated tree falls through to the per-section merge path.

- [x] **Fixed-unit credit pricing (monetization rework).** **DONE 2026-07-16** — replaced post-paid
  cost×rate metering with prepaid fixed prices (`core/pricing.py` price card: intake 2u, generate_fresh
  4u, regenerate 2u, score/extract/parse/ats/rematch/draft 1u), atomic upfront `debit_fixed` +
  refund-on-failure (`core/credits.py`, no negative balances), tiered signup grants and unit-denominated
  packs (`core/payments.py`), and a one-shot Alembic redenomination (`aa10units01`, ÷20 + top-up).
  Full suite green (1001 passed; pre-existing full-suite flake `test_run_scraper_continues_on_source_error`
  unrelated). Spec: `docs/superpowers/specs/2026-07-15-fixed-unit-pricing-design.md`.

- [x] **[audit P2] Standardize admin auth on `require_real_admin` (S4).** **DONE 2026-07-13** — deleted
  `require_admin` (resolved admin via `current_profile_id`, i.e. the impersonated tenant). Moved
  `require_real_admin` down into `credits.py` (base module, avoids the import cycle; `admin.py` re-exports
  it) and hardened it to read the session off `request.scope` so it no longer hard-requires
  SessionMiddleware. All six admin endpoints (`admin_grant`, `admin_set_tier`, `system_balance`,
  `invite_user`, `list_invites`, dev `resume_compare`) now use it. Regression tests added
  (`test_require_real_admin_*` in `test_impersonation_seam.py`); credits/invite/set-tier tests updated to
  gate via `require_real_admin`. Docs synced (`web/CONTEXT.md`). Full web suite 390 green.

- [x] **[audit P2] Dead-code sweep (R2/R3/R4).** **DONE 2026-07-13** — R2: deleted the orphaned
  throwaway `core/tree_render.py` + `tests/core/test_tree_render.py` (the dev compare harness now uses
  `core/tree_assembler`; only the test imported the module); `core/CONTEXT.md` reference removed. R3/R4
  were NOT dead — see the follow-up entry below.

- [x] **[audit P3] Guard `create_profile` to local-only (R3).** **DONE 2026-07-13** — decision confirmed:
  1 account = 1 profile. Corrected finding: the UI already enforces this (the "+ Create your profile"
  button in `UserHome.jsx` renders only when the user has zero profiles — bootstrap, not a switcher).
  The remnant was the backend `POST /api/config/profiles`, needed for the local/dev/tray bootstrap but an
  unscoped orphan-row creator in production (prod profiles come from `web/auth/identity._provision_profile`
  at login). Now returns 404 when `APP_ENV=production`; local bootstrap unchanged. Regression test added
  (`test_post_profile_blocked_in_production`). R4 needs no action — `_get_providers`/`_env_key_name` are
  still used by the local-mode setup-status probe and already commented.

- [x] **[audit P2] `print` → `logger.exception` in `routers/scraper.py` (I3).** **DONE 2026-07-13** —
  both broadcast-failure paths now use module `logger.exception` instead of bare `print(..., flush=True)`.

- [x] **[audit P3] Purge stale global prompt rows (S1 follow-up).** **DONE 2026-07-13** — Alembic migration
  `aa09rmprompts01` deletes the 10 legacy global-config keys (`{type}_prompts`, `active_{type}_prompt_id`,
  `{type}_prompt_template`, `latex_templates`) left by the removed picker. Runs on Railway startup
  (alembic-on-startup) and locally; per-tenant `profile_config` template copies untouched; downgrade is a
  no-op. Verified against an in-memory DB (stale keys gone, unrelated globals + per-tenant rows preserved).

- [x] **[audit P3] Meter the real extraction cost (I1).** **DONE 2026-07-13** — root cause: extraction
  (`_call_llm_for_extraction`) and `Job.match_profile_skills` do a direct `client.chat.completions.create`
  that never called `metering.record_call`, so the gated `extract` action always settled a 0 debit
  ("extraction is free"). Added a shared `core.llm.record_usage(response, model)` helper (session cost +
  meter), refactored `call_llm` onto it, and called it from both direct-call sites. Extraction + its
  skill-match sub-call are now billed. Regression tests in `test_metering.py`; docs synced
  (`core/CONTEXT.md`, `web/CONTEXT.md`). Full core+web suite 840 green.

- [x] **[audit P3] Auto-refresh navbar balance after a spend (I2, part 1).** **DONE 2026-07-13** — the
  navbar balance was SSE-blind to its own debits (lagged until the next reload/402). `meter_action` now
  broadcasts a content-free `credits` SSE event when a debit settles (best-effort; wrapped so a broadcast
  failure never affects billing, and the payload carries no balance since the SSE stream is a global
  broadcast — each client refetches its own authenticated `/api/credits`). `App.jsx` dispatches the
  existing `auto-apply:credits-stale` event on that message, which `CreditBalance` already listens for.
  Covers both synchronous actions (generate/extract/draft) and the background pipeline (score/eval/refine).
  Regression tests in `test_metering.py`. Remaining I2 items: refund clawback on chargeback (own feature).

- [x] **[audit follow-up, security] Tenant-scope the SSE stream (cross-tenant leak).** **DONE 2026-07-13** —
  `/api/events` was a global broadcast: every `job` event fanned a full, tenant-private payload
  (title/company/description/scores/salary/paths) to *all* connected clients, and since `job_key` is
  unique only per profile it could overwrite one tenant's job row with another's in the recipient's UI.
  Fix: `sse.subscribe`/`send` now carry a `profile_id`; `/api/events` subscribes with the caller's tenant;
  `job`/`credits`/`prompt_reset` events are scoped, genuinely-global events (LLM status) still broadcast.
  Separately re-keyed the `llm_status` in-flight registry by `(profile_id, job_key)` (it collided the same
  way) and scoped its `/api/llm-status` seed + `llm_status`/`llm_action` events. Tests:
  `test_sse_scoping.py`, updated `test_llm_status_router.py`. Full web+core suite 846 green.

- [x] **[audit follow-up, security] Namespace output artifacts by profile (file-path collision).**
  **DONE 2026-07-13** — output files were `generator/outputs/{job_key}_{name}` with no tenant dimension;
  two tenants sharing a `job_key` (unique only per profile) wrote the **same** PDF/MD, so the loser's
  `serve_resume` (passes the `Job.get` scope check but reads the shared file) returned the wrong tenant's
  document. Every built path is now `{profile_id}_{job_key}_{name}` across `core/job.py`,
  `web/intake_pipeline.py` turn snapshots, and `web/routers/jobs.py` serve/backfill/glob (~24 sites) +
  ~14 test files updated. Backward-compat: stored `resume_path`/`cover_path` are absolute so
  already-rendered docs keep serving; old-scheme files orphan harmlessly (`documents` is source of truth)
  and re-render into the new path — no prod migration needed. Full suite green (989; one pre-existing
  `test_logging_config`→`caplog` ordering flake in `tests/scraper`, unrelated).

- [x] **[audit 2026-07-15, security] Metering + tenant-scoping sweep (6 fixes).** **DONE 2026-07-15** —
  focused audit of profile scoping and LLM credit enforcement. Fixed: (1) `/ws/tray` websocket was
  unauthenticated in prod (websocket scopes bypass `AuthGateMiddleware`) and a global singleton leaking
  cross-tenant apply payloads — now refused with 4003 when `APP_ENV=production`; (2) ATS gate LLM call
  unmetered and free-triggerable via every résumé document save — now `meter_action(action="ats")`,
  skipped on insufficient credits; (3) résumé parse (`parse_propose` → `User.from_pdf/from_markdown`)
  had no meter/gate/`record_usage` — now `action="resume_parse"` + usage recorded (first onboarding
  parse is billable; signup grant covers it); (4) extraction's skill-match ran outside the settled
  extract meter (unbilled, contradicting audit I1) — now its own meter block; (5) `/api/session-cost`
  leaked platform-global spend — admin-only in prod, others get `{total: 0.0}` (heartbeat preserved);
  (6) deleted dead unscoped/unmetered `tray._gate_report_for` + its test. `web/CONTEXT.md` updated.
  Suite green (989; same pre-existing scraper caplog flake). Everything else checked clean: config/prompt
  ownership guards, skills/stats/scraper tenant filters, admin gates, Stripe webhook/verify, SSE scoping.

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
  extraction's debit always settled to 0 (fixed — audit I1); the navbar balance didn't auto-refresh
  after a successful action (fixed — audit I2, `meter_action` now broadcasts a `credits` SSE nudge).
  See `ARCHITECTURE.md` → "Credits & Metering", `core/CONTEXT.md`, `web/CONTEXT.md`.
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
