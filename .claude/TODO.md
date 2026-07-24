# TODO

Backlog for multi-session work. Update this file whenever scope changes or an item is completed:
mark items `[x]`, move them to **Done**, or revise scope notes inline. Prune stale done entries —
git history is the archive (see `.claude/skills/update-todo/`).

## Bugs

- [ ] **[deploy] Allowlist the pinned extension redirect URL on Railway + have users reinstall.**
  Follow-up to commit `be9bd72` (pinned Chrome `key`). For live extension sign-in to work, add
  `https://hhdmojkjnegdgdaacleldfgonicipnac.chromiumapp.org/` to `EXTENSION_REDIRECT_URLS` on Railway
  (production) — keep the existing Firefox value, comma-separated — and redeploy. After redeploy, users
  must re-download/reinstall the extension to pick up the pinned `key` (the ID only changes on a fresh
  load-unpacked). Until both are done, Chrome sign-in still 400s with a redirect-mismatch.

- [ ] **[audit 2026-07-19] Pre-existing order-dependent test failures (test pollution).** Both
  pass in isolation but fail in full-suite runs; present on clean HEAD before the dead-code
  cleanup:
  1. `tests/scraper/test_runner.py::test_run_scraper_continues_on_source_error` — caplog misses
     `scraper.runner` logs when the full suite runs.
  2. `react-dashboard/src/api.profileTree.test.js` "getProfileTree GETs the tree route".

- [ ] **Follow-ups for email deliverability (non-blocking).**
  1. **Verify auth in practice:** send a real invite to Gmail → "Show original" → confirm
     SPF/DKIM/DMARC all say PASS. Beats the Cloudflare dashboard widget (report-driven,
     24–72h lag; empty/stale until traffic flows).
  2. **Tighten DMARC to `p=quarantine`** after ~a week of clean aggregate reports.
  3. Ignore Cloudflare's "BIMI in use — fail" — BIMI is optional (needs `p=quarantine`+
     often a paid VMC cert); irrelevant to spam placement.

## Features

- [ ] **Usage-based (metered) LLM billing instead of fixed-unit prices.** Idea (2026-07-23): cap a
  call's `max_tokens` at whatever the user's remaining balance can afford, then debit dynamically
  from *actual* tokens used (from `usage` on the response) rather than a flat per-action unit price.
  This directly resolves the "fixed-price LLM oracle" risk (see Known accepted limitations) — no more
  worst-case-cost-vs-unit-price gamble — and lets long inputs (e.g. 4-page résumé parses) run as large
  as the balance allows. Design work: a token→credit conversion rate (with margin), pre-call balance
  gating on an *estimated* max (still needed so the call can't overspend), post-call reconciliation of
  the real cost, UX for "this action costs a variable amount," and how it coexists with / replaces the
  current prepaid fixed-unit model in `core/metering.py` + `core/pricing.py`. Bigger than a tweak —
  its own spec.

- [ ] **Robust error logging for Railway (hosted).** The local rotating-file logging
  (`core/logging_config.py`, "Structured error logging v1") doesn't help on Railway — the `/data`
  volume log file isn't easily inspectable and container restarts/redeploys scatter context. Build
  hosted-grade error observability: ensure tracebacks/`logger.exception` output reaches Railway's
  log stream (stdout/stderr JSON so it's queryable in the Railway logs UI), decide on structured
  (JSON) vs. plain formatting per env, and consider the deferred v2 from error-logging-v1 — a
  queryable DB error table + in-app admin viewer — so production failures are diagnosable without
  SSHing into the container. Scope: log routing/format by `APP_ENV`, request-context enrichment
  (profile_id, route, request id), and where errors surface (Railway stream vs. DB vs. admin UI).

- [ ] **Scrape buttons on individual job pages (extension).** The extension currently surfaces
  its Scrape affordance only in the job-search/results list. Add a Scrape button on the standalone
  job-detail pages too (LinkedIn/Indeed single-job views), so a user can capture a job they've
  navigated directly into without going back to search. Reuses the existing per-card scrape/stage
  flow; needs the detail-page DOM selectors + injection point.

- [ ] **Add Playwright testing suite.** Introduce end-to-end / browser-driven testing with
  Playwright to cover the React dashboard flows (and potentially the extension apply-form
  enumeration). Decide scope (E2E dashboard vs. component vs. ATS form-fill), CI wiring, and
  where fixtures/test data live.

- [ ] **Browser-extension DOM recalibration tool.** Extension selectors break whenever
  LinkedIn/Indeed reshuffle their (hashed) DOM. Add a "Recalibrate" affordance in the extension:
  the user clicks it and the extension walks through each DOM element it needs to read (title,
  company, location, description, apply button, …), prompting the user to click each element in
  turn; the extension captures a stable selector/anchor from the clicked node and persists it as
  an override. Also support a lighter path: when only a few reads are failing, let the user fix
  those individual elements one at a time rather than re-walking everything. (Motivated by the
  ATS-detection work — `getApplyInfo()` adds yet another fragile selector.)

- [ ] **Full automation of document submission** (personal tool use only). Fill in all the ATS
  fields for non-easy-apply jobs, avoiding LinkedIn native bot detection. **Decomposed into 5
  sequenced sub-projects** (each gets its own spec → plan → impl cycle; natural dependency order):
  1. **ATS detection & apply-URL resolution** _(DONE & shipped 2026-07-19; merged commit 13befaa)_
     — at scrape time, flag easy-apply vs. not, resolve the final apply-redirect URL, identify the ATS
     by domain (Greenhouse/Lever/Ashby/Workday/iCIMS/Taleo/…). Foundation for everything below;
     independently useful as a per-job label. Core/DB/API/UI fully implemented: `core/ats.py` (classify_ats + unwrap_apply_url), Alembic migration `aa12atsdetect01` (five new nullable columns), PATCH `/api/scraper/jobs/{job_key}/ats-resolution` endpoint, AtsChip React component, admin-only extension Live/Local server toggle (browser-extension serverMode storage + /api/ext/me returns is_admin). Spec/plan: `docs/superpowers/specs|plans/2026-07-19-ats-detection*`.
     **Manual smoke test:** Task 2 Step 6 PENDING maintainer execution (see `browser-extension/CONTEXT.md`).
  2. **Field-mapping engine** _(IMPLEMENTED 2026-07-20 on `feat/field-mapping-engine`; not yet merged to main)_ —
     maps profile + generated documents onto an ATS form → read-only `ApplicationPlan` (no form
     writing). All 12 plan tasks done: canonical taxonomy (`core/application_fields.py`), EEO
     guard + classifier (`core/application_classify.py`), `User.application_answers` profile section
     (eligibility + EEO, all optional), static schemas greenhouse/lever/ashby (`core/ats_schemas.py`),
     Pydantic models (`EnumeratedField`/`PlannedField`/`ApplicationPlan`), the pure engine
     (`core/application_mapper.py` — LLM-free, essay drafting injected), `Job.application_plan` column
     + migration `aa13applyplan01`, POST/GET `/api/scraper/jobs/{job_key}/application-plan` +
     `map_fields` metering (only when the essay pass runs) + `web/application_plan_service.py`, the
     read-only `ApplicationPlanModal.jsx`, the `ApplicationAnswers.jsx` settings section, and
     read-only browser-extension form enumeration + soft nudge. Backend 1074 pass / frontend 207 pass
     (the 2 remaining failures are pre-existing, unrelated: scraper caplog order-flake + `api.profileTree`).
     **Follow-ups before/after merge:**
     - **Enumeration-correctness gaps IMPLEMENTED 2026-07-22** (`feat/extension-enumeration-correctness`;
       plan `docs/superpowers/plans/2026-07-22-extension-form-enumeration-correctness.md`) — hardened
       the EEO guard (regex + real-label regression fixtures) and rewrote `enumerateForm()`
       (`browser-extension/content/form_enumerate.js`) to report logical field types
       (`combobox`/`multiselect`/`select`/`radio_group`/`checkbox_group`/`checkbox`), ARIA-aware
       `required`, de-noised labels, radio/checkbox grouping, and to skip anonymous combobox partner
       inputs (comboboxes ship read-only `options: []`, no focus-harvesting). Unit-tested in
       `e2e/extension/tests/enumerate.spec.ts`. See `browser-extension/CONTEXT.md` for the accurate
       enumeration behavior. **Still open:** broadening label→canonical classification (essay-bucket
       catch-all, sub-project 3 above) and the form-fill/submit-commit stage (sub-project 3 below) —
       this task only hardened read-only enumeration.
     - **PENDING manual smoke test** of the extension enumeration flow against real Greenhouse/Lever/Ashby
       apply pages (selectors + job→page matching untested on live DOM) — see `browser-extension/CONTEXT.md`.
     - **`ApplicationAnswers` mounted UNGATED** — spec wanted it friends_family/beta-gated, but no
       client-side tier-gating mechanism exists in the dashboard; gate it when one is introduced.
     Spec: `docs/superpowers/specs/2026-07-20-field-mapping-engine-design.md`; plan: `docs/superpowers/plans/2026-07-20-field-mapping-engine.md`.
  3. **Form-fill + submit automation** — drive the form per-ATS; start with the low-defense
     form-based ATSs (Greenhouse/Lever/Ashby, mostly no login), fall back to manual for the rest.
  4. **Credential vault** — store logins for account-based ATSs (Workday/iCIMS/Taleo).
     Client-side-only in the extension, encrypted, never sent to the server (security liability).
  5. **Submission confirmation** — detect success and auto-mark applied (see extension CONTEXT
     "Auto-mark as applied on submission" future-work note).

- [ ] **Gate the per-prompt user model override to admins only.** The model-override control on
  prompts should be admin-only for now — regular users shouldn't pick their own model until
  tiered-model pricing is worked out (different models cost different credits). Revisit once
  pricing per model tier is designed (see the "High-effort toggle" item — same underlying
  cost-vs-quality knob). _Partially mitigated 2026-07-18:_ a server-side model allowlist
  (`LLM_ALLOWED_MODELS`; prod default = `LLM_DEFAULT_MODEL` only) now bounds what users can
  pick — see the audit entry in Done. The UI control + tier pricing question remains open.

- [ ] **Guided section-prompt authoring for users (from the prompt-polish work).** Once we've
  settled how to best structure section/item prompts (baseline-facts + tailoring direction;
  honesty rules re: seniority/titles and proof-words; per-project technology surfacing), give
  that structure to users instead of a blank textarea. Two options to explore:
  1. **Pre-formatted template** — when a user adds/edits a section or list item, pre-fill the
     prompt field with the agreed structure (labeled "Baseline facts", "What to emphasize",
     "Do NOT claim", etc.) for them to fill in.
  2. **Full GUI questionnaire** — a guided form that asks plain questions ("What exactly did
     you do?", "What technologies did you use?", "What should we NOT claim about this role?")
     and compiles the answers into a well-formed section/item prompt. Lowers the skill floor
     and enforces the honesty structure by design.
  Reference the live profile-9 section/item prompts as the worked example of the target format.

- [ ] **Pin / promote a generated value as the field's default, and use default text as a
  generation baseline.** Two related gaps in the section-generation model:
  1. **Promote-to-default:** when a user likes a particular LLM output for an item field,
     give them a way to save it back as the field's stored `value` — optionally flipping the
     field to non-LLM-output so it renders verbatim and is no longer regenerated.
  2. **Default-as-baseline:** an LLM-output field's current stored `value` is NOT shown to the
     generator. Consider feeding it in as an optional baseline ("improve on this, don't discard
     it"). Decide the semantics vs. the item `prompt` (which currently carries baseline facts).
  Note: today, non-LLM-output fields render verbatim; LLM-output fields ignore the prior value.

- [ ] **Re-parse résumé into an existing populated profile.** Backend `parse/apply` already
  supports it (add-only-safe skip defaults), but only onboarding + the new-profile wizard surface
  the parse UI. Add a re-parse button in the profile/settings UI. (Follow-up from the profile
  schema engine #5 onboarding-parse work — the #1–#6 tree swap itself is complete and live.)

- [ ] **High-effort toggle.** A toggle (per-prompt and/or a general switch) that swaps to a
  more capable model for a request, consuming more credits in exchange for higher quality.
  Surface the cost implication in the UI (natural fit with the fixed-unit price card —
  e.g. a higher-priced `generate_fresh_hq` action).

- [ ] **Feedback tab → admin ticketing.** Add a Feedback link in the navbar where users
  submit suggestions. Submissions become tickets visible in the Admin tab. A ticket has a
  sender, title, and description; admins can mark tickets completed and add notes. (New
  `tickets` table; user submit endpoint + admin list/update endpoints; navbar entry + admin panel.)

- [ ] **Improve the document feedback system.**
  _Current system:_ In `DocumentModal`, the user attaches free-text notes to items or whole
  sections (+ cover-letter box). Submitting batches notes to `POST /{doc_type}/feedback`; each
  becomes a `{category:"user_feedback"}` issue fed to the existing refine prompt as a one-shot
  `run_user_feedback_refine` (now a single prepaid `regenerate` (2u) action). No feedback-specific
  prompt, no preview/diff, no per-note accept/reject, no history.
  _Possible improvements:_ a dedicated feedback-refine prompt for localized edits; diff/preview
  before committing; per-note apply/skip; multi-turn feedback; surface which notes the model
  addressed; richer anchors than a text label.

- [ ] **Persistent user memory** — Store durable user directives, e.g. "Never say this",
  "This project is my best portfolio piece". Referenced by the LLM during generation.

- [ ] **User skill interview** — Combines job analysis + persistent memory. Interview the user on
  comfort level with specific techs; confidence tier governs how the LLM references them
  (omit low-confidence, slight upsell on mid-confidence, full claim on high-confidence).

- [ ] **Nicer process/skill formatting** — Format process descriptions with more tables, fewer
  bullet points, less prose. Condense phrasing:
  "Strong proficiency in Python" → "Python",
  "Hands-on experience with LLMs and generative AI" → "LLMs, generative AI".

### Hosting / SaaS conversion

Stack complete and live at `https://autoapply.matthewbarlow.me`:
**Multi-tenancy ✅ → Hosting ✅ → (1) Auth ✅ → (2) Credits ✅ → (3) Payments ✅ → (4) Onboarding ✅**
(guided tour, demo job, resume-upload first-run, all three job-ingestion paths). Monetization now
runs on prepaid fixed-unit pricing (see Done). Specs/plans under `docs/superpowers/`;
architecture in `docs/ARCHITECTURE.md`; read `web/CONTEXT.md` → Auth / Credits before touching those.

Known accepted limitations (each would be its own feature if prioritized):
- No automatic credit clawback on Stripe refunds/chargebacks (admin-manual).
- Free non-LLM endpoints are not rate-limited.
- [audit 2026-07-18] Prompt content is fully user-authored and runs on the platform key at flat
  unit prices (fixed-price LLM oracle). Accepted 2026-07-19: fine as long as worst-case output
  cost per call stays below the unit price (allowlisted cheap models keep this true — recheck
  if the allowlist ever adds a pricier model or max_tokens grows).
- Stripe dashboard product names/descriptions may still mention pre-redenomination credit
  counts — check in the Stripe dashboard (app UI is authoritative).

## Done

- [x] **Pin Chrome `key` in extension manifest to stabilize the OAuth redirect URL.** **DONE 2026-07-23**
  — commit `be9bd72`. Chrome load-unpacked derived the extension ID from the install path, so every
  machine got a different `chrome.identity.getRedirectURL()` that fell off `EXTENSION_REDIRECT_URLS`
  and 400'd sign-in. Added a fixed `"key"` to `browser-extension/manifest.json`, giving a constant
  extension ID (`hhdmojkjnegdgdaacleldfgonicipnac`) and redirect URL
  (`https://hhdmojkjnegdgdaacleldfgonicipnac.chromiumapp.org/`) across machines. Private key at
  `backups/extension_key.pem` (gitignored) — kept for store publishing. Resolved the "pin a Chrome
  `key`" Future Work item in `browser-extension/CONTEXT.md`. **Still open (deploy step):** the stable
  redirect URL must be added to `EXTENSION_REDIRECT_URLS` on Railway (production) or live sign-in still
  400s, and users must re-download/reinstall the extension after redeploy — see the open action below.

- [x] **Stamp unique item order in parsed list sections (parse/apply 422 fix).** **DONE 2026-07-23**
  — commit `a9d7f60`. A novel résumé "list" section (e.g. CERTIFICATIONS) with 2+ rows built item
  `GroupNode`s with no `order`, all defaulting to 0; `validate_tree` rejects a `ListNode` whose
  children share a sibling order, so `parse/apply` raised a 422 with **no server log** — surfacing as
  a phantom "can't parse résumé" failure. Two fixes in `core/parsed_sections.py`:
  `build_section_from_parsed` stamps `order=entry_idx` on each list item, and `merge_section`
  re-indexes item order after extending (raw extend collided 0..n twice). Regression tests for both
  paths in `tests/core/test_parsed_sections.py`. Also documented the silent-422 logging gap in
  `web/CONTEXT.md` → Known Issues (both `parse_apply` validation branches raise without logging;
  add a `logger.warning` before the raise when next touching that code).

- [x] **Raise résumé-parse token budget and guard truncation.** **DONE 2026-07-23** — commit
  `e424d19`. A 4-page résumé overflowed `User.from_markdown`'s 8000-token output cap, truncating the
  structured JSON (`finish_reason='length'`) and surfacing as a 422 "invalid JSON". Raised
  `max_tokens` 8000→32768 and `timeout` 30→90s, and added a `finish_reason == "length"` check that
  raises a clear `ValueError` ("Résumé parse truncated…") instead of a confusing downstream
  JSON-parse error. Small hardening; documented in `core/CONTEXT.md` → Key Invariants.

- [x] **Log resume parse failures before returning 422.** **DONE 2026-07-23** — commit `b84ed6a`.
  `POST /api/config/profiles/{id}/parse/propose` (`web/routers/config.py`) returned 422 with the
  error only in the response body; server-side logging never recorded it, so production parse
  failures were invisible in the Railway logs. The `except (ValueError, RuntimeError)` block now
  logs a WARNING (profile id, file suffix, exception) via a new module-level `logger` before
  raising. Observability-only; no behavior change.

- [x] **Extension autofill hardening — per-field error isolation + checkbox match fix.** **DONE 2026-07-21**
  — commit `7342b74`. `fillForm()` (`browser-extension/content/form_fill.js`) now wraps each field's
  `_findControl`/`_writeValue` in try/catch so one control throwing (e.g. a file input rejecting a
  programmatic `.value` write — greenhouse/lever/ashby static schemas all declare a required
  resume/resume_file field) no longer aborts the loop and strands subsequent fields. Also tightened
  `_writeValue`'s checkbox/radio branch: `value === "true"` previously matched *any* checkbox/radio
  regardless of the control's own DOM value; now it only matches boolean-style controls whose own
  value is `""`, `"on"`, or `"true"`, so it no longer overreaches into real radio-group options.
  Verified via `e2e/extension/`'s `autofill.spec.ts` (greenhouse/lever/ashby fixtures) +
  `extension-loads.spec.ts` — all 4 tests pass.

- [x] **Extension ATS autofill harness — Task 5 (Lever/Ashby specs, docs, doc-sync).** **DONE 2026-07-21**
  — Parametrized `e2e/extension/tests/autofill.spec.ts` over all three fixtures (greenhouse, lever,
  ashby), each with its own `JOB_KEY`/apply URL/route glob/before-after screenshot pair; all three
  pass, asserting the per-ATS canonical email field fills (Ashby's React-controlled
  `_systemfield_email` confirmed via the native-setter write path). Found and fixed a real bug along
  the way: `core/ats_schemas.py`'s `ashby` static schema used generic field ids (`name`/`email`/
  `phone`) that don't match the live DOM (`_systemfield_name`/`_systemfield_email`/
  `_systemfield_phone`), so `form_fill.js`'s `[name=...]`/`getElementById` lookup could never find
  the control — the static-schema fill silently failed even though the field existed. Fixed to use
  the real DOM ids (matches the convention already followed by greenhouse/lever's schemas). New
  `e2e/extension/CONTEXT.md` documents the harness (persistent-context extension load, storage-key
  seeding, canonical-fields-only-fixtures ⇒ no-LLM invariant, how to add an ATS). Corrected a
  misleading prior smoke-test note in `browser-extension/CONTEXT.md` — the 2026-07-20 "Live-DOM
  enumeration validated" entry exercised `enumerateForm()` by direct injection, not through the real
  content-script trigger path (broken until Task 4's `setTimeout` fix); reworded so the record isn't
  taken as live-path validation. Added a `browser-extension/CONTEXT.md` subsection documenting
  `form_fill.js` (status filter, control lookup order, native-setter write, EEO-never-inferred rule)
  and a Future Work item flagging that the `http://localhost:8080/*` `host_permissions` entry ships
  in the production manifest and must be reviewed/removed before store packaging. **Sub-project 3's
  extension autofill-writer 5-task plan is now complete.** Remaining gaps (tracked, not blocking):
  multi-step/wizard ATS forms are unsupported; essay/custom-field drafting is untested by this
  harness (fixtures are canonical-only by design); live (non-fixture) end-to-end verification is
  still open (see `browser-extension/CONTEXT.md` → "Full-pipeline steps still to verify manually").

- [x] **Extension ATS autofill harness — Task 4 (autofill writer + wiring + spec).** **DONE 2026-07-21**
  — commit `a6a7d18`. New `browser-extension/content/form_fill.js`: content-script global
  `fillForm(plannedFields) -> {filled: number}` writes an `ApplicationPlan`'s resolved values into
  the live ATS form (native-setter + input/change events for React-controlled inputs; handles
  text/textarea/select/checkbox/radio); only writes fields with status `filled`/`drafted` and a
  non-empty value. Registered in `manifest.json`'s ATS `content_scripts` entry after
  `form_enumerate.js`. `service_worker.js`'s `handleEnumerateForm` now reads the plan POST response
  body and returns its `fields` array (previously discarded); `injector.js`'s
  `_runFormEnumeration` calls `fillForm(result.fields)` on success. New
  `e2e/extension/tests/autofill.spec.ts` drives a live Greenhouse fixture end-to-end and asserts
  `#email` gets filled. Fixed two real (non-test-only) bugs found along the way: (1) `manifest.json`
  `host_permissions` was missing `http://localhost:8080/*`, so the extension's "local mode"
  server-routing toggle silently failed — Chrome blocks CORS-exempt fetches to hosts not listed
  there, and the local FastAPI server sends no CORS headers; (2) `injector.js` called
  `_maybeEnumerateApplyForm()` synchronously at script-load time, but content scripts in one
  manifest entry share an isolated world and run in file order (injector.js →
  form_enumerate.js → form_fill.js), so `enumerateForm`/`fillForm` weren't defined yet — form
  enumeration (shipped in a prior task) had never actually run at runtime. Now deferred via
  `setTimeout(_maybeEnumerateApplyForm, 0)`. **Task 5 (Lever/Ashby specs + docs) not started** —
  see `.superpowers/sdd/progress.md` in the `extension-ats-e2e` worktree.

- [x] **Extension ATS autofill harness — Task 3 (harness scaffold + smoke spec).** **DONE 2026-07-21**
  — commit `95395e8`. New `e2e/extension/` Playwright project (separate from the dashboard harness
  at `e2e/`): `playwright.config.ts` launches a **persistent Chromium context** with the unpacked
  `browser-extension/` loaded (required for MV3 service-worker registration — headed only, no
  headless support), `fixtures.ts` exports a `context`/`serviceWorker` fixture pair for reuse by
  the upcoming autofill spec, and `tests/extension-loads.spec.ts` smoke-asserts the service worker
  registers with a `chrome-extension://` URL. Reuses backend readiness (`GET /health`) and the
  Task 1 dev endpoints. Run via `cd e2e/extension && npm test`. Task 2 (ATS fixture HTML under
  `e2e/extension/fixtures/`) was already present. Task 4 (autofill spec) completed above.

- [x] **Extension ATS autofill harness — Task 1 (dev seed endpoint).** **DONE 2026-07-21**
  — commit `d57c70a`. Added non-production-only `POST /api/dev/seed-ats-job` (`web/routers/dev.py`,
  same `APP_ENV=production` 404 guard as `dev-login`): upserts a `Job` on the caller's profile from
  `{job_key, apply_url, ats_type}` with `state="scraped"` (literal string — `JobState` has no
  matching enum member) + `apply_url_raw`/`apply_url_resolved`/`ats_type`, idempotent. Lets a
  Playwright/extension harness stage a job, then drive an ATS apply page and request its
  `application_plan`. Tests in `tests/web/test_dev_seed_ats.py`. Docs in `web/CONTEXT.md` → Dev
  Endpoints and `.claude/CLAUDE.md` routing table. Part of the 5-task plan
  `docs/superpowers/plans/2026-07-21-extension-autofill-harness.md` (fixtures, harness scaffold,
  autofill writer + wiring, Lever/Ashby specs + docs still to come).

- [x] **Playwright smoke + live-drive E2E harness.** **DONE 2026-07-21** — commit `e5239d1`.
  New top-level `e2e/` Playwright project: config auto-boots/reuses the local stack (uvicorn `:8080`
  + Vite `:5173`), non-destructive smoke specs (landing `/about`, dashboard nav, Find-Jobs search UI),
  and a `global-setup` that logs in once and saves `storageState`. Added a **non-production-only**
  `POST /api/dev/login` (`web/routers/dev.py`) that sets `session["account_id"]` for local E2E —
  needed because the identity gate (`/api/me`) has no dev bypass, unlike the `current_profile_id`
  tenancy seam. Usage docs in `e2e/README.md`; caveats in `e2e/CONTEXT.md`. This is a smoke/ad-hoc
  drive harness, **not** a run-on-every-change regression suite.
  **Check-pages harness enhancements (commit `e1e350e`):** `npm run deck` (`e2e/scripts/deck.mjs`)
  builds a self-contained HTML slide deck from `screenshots/*.png` (filter arg shows one shot);
  the landing spec now settles load/scroll animations (scroll + `document.getAnimations()` +
  paint delay, dropped `networkidle` which never fires under Vite HMR) before its full-page shot;
  and `dev-login` resolves the account by `E2E_LOGIN_EMAIL` (default owner) → admin → first, plus
  provisions a throwaway account/profile on an empty DB to drive new-user onboarding.

- [x] **Focus Skills-section generation on relevant skills only.** **DONE 2026-07-19** — commit
  `b76e817`. Rewrote `SECTION_PROMPT_DEFAULTS["skills"]` (`core/section_presets.py`): ≤5
  job-relevant categories, most-relevant first, omit categories the job doesn't call for (e.g.
  frontend for a backend role), **exclude soft/interpersonal skills entirely** (teamwork/
  communication/adaptability/problem-solving — those belong in summary + cover), cap ~5 lines,
  inventory-only. The `skill_relevance (Skills)` eval check in `prompts/defaults/resume_eval_sectioned.md`
  now flags whole irrelevant categories, soft skills, and over-length (>~5 lines/5 categories);
  the `hallucination` line clarified to never flag soft skills as hallucinations. Per-profile DB
  data (local SQLite profile 9 + LIVE Railway Postgres profile 1 Skills-section + eval prompts)
  updated out-of-band (not tracked in git).

- [x] **Tune Skills-section to include role-common + staple skills (fix overshoot).** **DONE 2026-07-19.**
  Follow-on to `b76e817`: it overshot to ~5 skills. Reworded `SECTION_PROMPT_DEFAULTS["skills"]`
  and the `skill_relevance` eval check so a skill is included when it is (a) named in the job,
  (b) commonly expected for the target role/title, or (c) a core programming/tooling staple (Git,
  Docker, CI/CD, pytest) — provided it is in the inventory; dropped the "~5 lines" cap for a
  "roughly 4–5 categories, ~12–18 skills" target; eval no longer flags role-relevant tooling/
  staples as bloat. Local SQLite profile 9 Skills-section prompt updated out-of-band (backup in
  `backups/`). LIVE Railway Postgres profile 1 (Master / barlowmatt96) Skills-section + per-profile
  `resume_eval_sectioned` prompts synced to the new wording out-of-band 2026-07-19 (safety copies in
  `backups/live_profile1_*`).

- [x] **Skill-chip parsing splits parenthesized lists.** **DONE 2026-07-19** — commit `70ff26f`.
  Added paren-aware `split_skill_tokens` in `core/skill_analytics.py`: `Category (a, b)` now
  emits clean chips `Category`, `a`, `b`; unbalanced parens fall back to plain comma split;
  case-insensitive order-preserving dedupe. Wired into all skill readers (`job_has_skill`,
  `aggregate_skill_frequency`, and `core/job.py` skill-match chips / ATS lists / extraction
  prompt sections / `serialize`), so already-stored rows are repaired read-side — no migration.
  Phrase fields (`_split_ext_phrases`) untouched. Tests in `tests/core/test_skill_analytics.py`.

- [x] **[audit 2026-07-19, dead code] Dead-code audit cleanup.** **COMPLETE 2026-07-19** —
  commits `e93318c`, `fbd8a4b`, `4c99550`, `8fcbd9e`, `cc417a2`.
  - `8fcbd9e`: removed superseded `core/job.py` legacy methods — `save_batch`
    (`save_batch_returning` is the sole path), `get_or_raise`, `list_for_review`, `set_state`,
    `generate_resume_docx`, `_build_frontmatter`, stray `warnings` import; deleted
    `tests/core/test_resume_docx.py`, migrated batch-save tests. The md eval/refine methods
    (`evaluate_resume_md`/`evaluate_cover_md`/`refine_cover_md`/`_refine_doc_md`) were KEPT —
    dispatched dynamically via `getattr(job, f"evaluate_{doc_type}_md")` in
    `web/intake_pipeline.py`.
  - `cc417a2`: swept unused helpers — `User.load_from_json`, `core/utils.strip_header_block`,
    `core/stripe_client.retrieve_price`, `core/session_cost.get_session_start`,
    `web/llm_status.is_processing`, `generator/themes.get_theme`,
    `core/output_formats.DEFAULT_FORMAT_ID`, and `web/routers/config.py`'s `_set`/`_set_global`
    (orphaned by the route removal; `_get`/`_get_global`/`_get_providers`/`_read_env`/
    `_env_key_name` kept — imported by `jobs.py`/`setup_status.py`). Removed unused
    `deleteProfile`/`getDefaultPrompt` exports from `react-dashboard/src/api.js` (backend routes
    kept). Wired `ws.stop` into `tray_app/main.py` aboutToQuit. Pruned matching tests; rewrote
    `tests/web/test_profile_config_access.py` to seed rows directly.
  - Deliberately KEPT (verified live or intentionally retained): `User.education_degrees`
    (`{user.education_degrees}` in eval prompt templates), `GET /extension/download` (linked from
    the served "Browser Extension" Obsidian doc), `core/credits.CREDITS_PER_DOLLAR`
    (documentation) and `reconcile_balance` (billing-ops repair helper, no endpoint),
    `document_builder.apply_resume_patch` (retained per 2026-06-22 plan pending separate
    approval).
  - Two pre-existing order-dependent test failures discovered (not caused by this cleanup) —
    tracked under Bugs.

  Earlier in the same audit — deleted unconsumed endpoints from `web/routers/config.py`:
  `GET/PUT /api/config/{templates,scoring,sources,search,job_searches}`, `GET /api/job-fields`,
  `GET /api/user-profile-fields`, `GET /api/config/profiles/{id}/file` — superseded by the
  profile-tree API (`/api/config/profiles/{id}/tree`) and the scraper router; scoring weights are
  still read internally from `profile_config`. Orphaned tests removed
  (`tests/web/test_config_api.py`, `tests/web/test_config_tenant_isolation.py`,
  `serve_profile_file` cases in `test_profile_api.py` / `test_profile_tenant_scoping.py`).
  Commits `e93318c`, `fbd8a4b`; details in `web/CONTEXT.md` → Known Issues.
  Continued (`4c99550`): removed legacy `POST /api/admin/credits/grant` and
  `POST /api/admin/credits/tier` from `web/routers/credits.py` (no consumers; AdminPage uses the
  budget-checked `POST /api/admin/users/{profile_id}/grant` in `web/routers/admin.py`). Tier
  changes now have no API surface — set `Account.tier` directly if needed. Deleted
  `tests/web/test_admin_set_tier.py` and pruned the two admin-grant tests from
  `tests/web/test_credits_api.py`.

- [x] **[audit 2026-07-18, security] Residual hardening (findings 2 & 3).** **DONE 2026-07-19** —
  `require_real_admin` no longer falls back to the dev-tenant account under `APP_ENV=production`
  (sessionless request → 403 even if the outer auth gate is ever bypassed;
  `tests/web/test_admin_prod_fallback.py`), and `web/main.py` logs a startup warning when
  production resolves `CREDIT_DEFAULT_RATE <= 0` (billing silently off;
  `tests/web/test_billing_disabled_warning.py`). Finding 1 (user-authored prompts as a
  fixed-price oracle) accepted — see Known accepted limitations.

- [x] **[audit 2026-07-18, security] Payment-bypass sweep (2 fixes).** **DONE 2026-07-18** —
  full-codebase audit (secrets / tenant bleed / LLM billing bypass). Fixed the two exploitable
  holes: (1) **unclamped refinement settings** — `resume/cover_refine_max_turns` and pass scores
  from the user-writable profile blob fed the unmetered post-generation refine loop (unlimited
  free LLM calls per flat-priced generation); now clamped on hydrate to 0–5 turns / [0,1] score
  (`core/user.py`, `MAX_REFINE_TURNS`); (2) **free-text prompt-slot models** on the platform key —
  now validated against `core.llm.allowed_models()` (`LLM_ALLOWED_MODELS` env; prod default =
  `{LLM_DEFAULT_MODEL}`; local unrestricted) at `PUT /api/prompts` (422) and again at
  `get_client_for_profile` (stale rows fall back to default). Tests:
  `tests/core/test_refine_clamp.py`, `tests/core/test_model_allowlist.py`, prompts-router cases.
  Secrets, tenant scoping, SSE, payments webhook, admin gates all checked clean; three accepted
  residual risks logged under Known accepted limitations above.

- [x] **[audit 2026-07-18, security] Pre-beta tenant-isolation + file-read holes.** **DONE 2026-07-18** —
  closed two classes of pre-beta holes: (A) **arbitrary file read** — `serve_profile_file`
  (`GET /api/config/profiles/{id}/file`) now contains the served path to `profiles/`
  (`is_relative_to`, 404 otherwise), and `_reject_foreign_file_pointers` (called in
  `update_profile` PUT) 422s any client-supplied `resume_path`/`md_path`/`cover_letter_path`
  outside `profiles/` at the write boundary — blocking reads of the platform `.env` via the
  file-serve and résumé-parse sinks; (B) **cross-tenant leak/corruption** — `POST /skills/owned`,
  `POST /skills/profile`, `DELETE /skills/profile`, and `POST /api/profile/export-master` now
  inject `current_profile_id` into `User.load` instead of defaulting to profile 1. Regression
  tests added (`tests/web/test_profile_api.py`). Details in `web/CONTEXT.md` → Known Issues.

- [x] **Tier-gate browser-extension docs.** **DONE 2026-07-18** — split the extension
  install/usage guide out of Getting Started into its own `Browser Extension.md`
  (frontmatter `tiers: friends_family, beta`), rewritten for extension v1.1.0 (OAuth popup
  sign-in, Scrape-button flow/states, clear-history). `web/routers/docs_router.py` now honors
  a `tiers:` frontmatter key: gated docs are filtered from `GET /api/docs` and 403 on direct
  `GET /api/docs/{filename}` unless the caller's account tier matches (admins bypass). Getting
  Started keeps the tier-agnostic manual-upload path.

- [x] **Upload modal UX: backdrop-close + refresh.** **DONE 2026-07-18** — Pipeline's manual
  `UploadModal` now closes on backdrop click; a successful (non-duplicate) upload fires an
  `onUploaded` callback (Pipeline → App) that refetches jobs so the new card appears immediately
  instead of waiting on SSE. Empty-Inbox help link repointed to `/docs#adding-jobs`.

- [x] **Drop registered invitees from admin Invited list.** **DONE 2026-07-18** —
  `admin.list_invites` (`GET /api/admin/invites`) now excludes any allowlisted email that already
  has an `Account`, so a user leaves the Invited list once they sign in and appear under Users.

- [x] **Manual upload 502 during deploy window.** **DONE 2026-07-18** — manual job uploads that
  landed mid-Railway-restart got a raw 502 (proxy had no healthy upstream). `_fetch`
  (`react-dashboard/src/api.js`) now supports opt-in `retries`/`retryDelay` and retries only
  gateway statuses (502/503/504) with linear backoff; thrown errors carry `err.status`. Enabled on
  `uploadJob` (`retries:3`), which is idempotent server-side (deduped by URL).

- [x] **User View name stale after résumé parse.** **DONE 2026-07-18** — `UserHome` fetched
  profiles only on mount, so post-onboarding the "Welcome back {name}" header showed the pre-parse
  name until a manual refresh. `Wizard` `onFinish` now dispatches `auto-apply:profile-updated`
  (instead of reloading the page); `UserHome` listens and refetches profiles + its `usePrerequisites`
  so the header updates in place. Test: `UserHome.refresh.test.jsx`.

- [x] **Add search function to skill list.** **DONE 2026-07-18** — `TagListField`
  (`react-dashboard/src/components/widgets/profile-tree/fieldWidgets.jsx`) now live-matches the
  "Add…" draft against existing chips: partial matches highlight (ring), non-matches dim, and an
  exact case-insensitive duplicate shows an "Already in your list" hint and is blocked from being
  re-added. Client-side (no network); generic across all taglists. Tests in `fieldWidgets.test.jsx`.

- [x] **Hosted-DB extraction prompt stale.** **DONE 2026-07-18 (deploys on next release)** —
  Alembic migration `aa11extract01` refreshes every `prompts`/`prompt_defaults` extraction row
  whose content is byte-for-byte the old factory default to the new atomic-skill default
  (rstrip-tolerant match; user-customised prompts left untouched; reversible). Runs automatically
  via alembic-on-startup on the next Railway deploy.

- [x] **Job view chips false amber on owned skills.** **DONE 2026-07-18** — root cause was
  extraction emitting verbose phrases ("Strong proficiency in Python") and comma-bearing
  parentheticals into `ext_required_skills`, so the whole-phrase `skill_key` never matched a
  profile skill and the chip showed a false résumé gap. Two-layer fix: (A) `owned_skills` now
  recovers ownership when an owned skill key appears as a bounded word inside a multi-word phrase
  (`web/routers/skills.py`, tests in `tests/web/test_skills_api.py`); (B) tightened the extraction
  prompt (`prompts/defaults/extraction.md`) to require atomic skill tokens, no qualifiers,
  no bundled/parenthetical/comma entries — also updated the local DB copies. Hosted-DB migration
  tracked as an open Bug above.

- [x] **Fixed-unit credit pricing (monetization rework).** **DONE + DEPLOYED 2026-07-16** —
  replaced post-paid cost×rate metering with prepaid fixed prices (`core/pricing.py` price card:
  intake 2u, generate_fresh 4u, regenerate 2u, score/extract/parse/ats/rematch/draft 1u; standard
  job = 10u), atomic upfront `debit_fixed` + refund-on-failure (`core/credits.py`, no negative
  balances), tiered signup grants (20/50/200) and unit-denominated packs (`core/payments.py`,
  net ÷ $0.02 × tier multiplier), price hints + price-aware 402 toast in the UI, and a one-shot
  Alembic redenomination (`aa10units01`, ÷20 + top-up) — **ran against live Postgres; verified**
  (beta account topped to 200u, ledger invariant holds). Suite 1001 green.
  Spec: `docs/superpowers/specs/2026-07-15-fixed-unit-pricing-design.md`.

- [x] **[audit 2026-07-15, security] Metering + tenant-scoping sweep (6 fixes).** **DONE 2026-07-15** —
  fixed: unauthenticated `/ws/tray` in prod (now 4003) + cross-tenant apply-payload singleton;
  unmetered ATS gate; unbilled résumé parse; skill-match outside the extract meter; `/api/session-cost`
  leaking global spend (admin-only in prod); dead unscoped `tray._gate_report_for`. Everything else
  checked clean (config/prompt ownership, tenant filters, admin gates, Stripe webhook, SSE scoping).

- [x] **[audit 2026-07-13] Full codebase audit + all follow-ups.** Findings doc
  `docs/audit-2026-07-13.md` (S1–S5/R1–R4/I1–I4); every actionable item completed 2026-07-13/15:
  global-config prompt surface deleted (S1 + `aa09rmprompts01` purge), `draft` metered (S2),
  server-derived `is_onboarding` (S3), `require_real_admin` standardized (S4), dead-code sweep
  (R2–R4), extraction cost metered (I1), SSE credits nudge for navbar balance (I2), scraper
  `logger.exception` (I3), tenant-scoped SSE stream + profile-namespaced output artifacts
  (cross-tenant leak fixes). Details in git history and `web/CONTEXT.md`.

- [x] **Structured error logging v1** (2026-07-12) — `core/logging_config.py` rotating-file +
  excepthooks, wired at web/tray startup; `logger.exception` on failure paths. Root causes of the
  motivating bugs also fixed (extraction truncation retry; SQLite WAL/busy_timeout). Deferred v2:
  queryable DB error table + dashboard viewer.

- [x] **Profile Schema Engine #1–#6** (June 2026, pushed) — user-defined recursive résumé tree
  end-to-end: schema engine, builder UI, per-section LLM generation + prompts, tree-v1 rendering/
  refinement/ATS/feedback (retired typed `ResumeDocument` path for new docs), onboarding parse,
  live PDF preview, output formats + résumé themes. Specs/plans under `docs/superpowers/`.
