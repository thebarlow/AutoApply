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

- [ ] **[deploy] Verify on Railway that `ADMIN_EMAILS` includes the owner before deploying the
  admin re-sync** (commit `222fe05`). `sync_admin_flag` now promotes *and demotes* on every login;
  if the owner isn't in `ADMIN_EMAILS` (and has no admin `allowed_email` invite row) they lose admin
  on next login.

- [ ] **[deploy] Confirm the PDF preview iframe still renders in Chrome and Firefox on the live
  site** with the new security headers (commit `6d51b91`). PDFs get `X-Frame-Options: SAMEORIGIN` +
  `frame-ancestors 'self'`; everything else is `DENY` / `frame-ancestors 'none'`.

- [ ] **[audit 2026-07-19] Pre-existing order-dependent test failures (test pollution).** Both
  pass in isolation but fail in full-suite runs; present on clean HEAD before the dead-code
  cleanup:
  1. `tests/scraper/test_runner.py::test_run_scraper_continues_on_source_error` — caplog misses
     `scraper.runner` logs when the full suite runs.
  2. `react-dashboard/src/api.profileTree.test.js` "getProfileTree GETs the tree route".

- [ ] **`account_email` in `error_events` is new PII at rest.** Admin-gated today; flag for
  the eventual data-retention/GDPR pass (retention window, export/delete-on-request).

- [ ] **Follow-ups for email deliverability (non-blocking).**
  1. **Verify auth in practice:** send a real invite to Gmail → "Show original" → confirm
     SPF/DKIM/DMARC all say PASS. Beats the Cloudflare dashboard widget (report-driven,
     24–72h lag; empty/stale until traffic flows).
  2. **Tighten DMARC to `p=quarantine`** after ~a week of clean aggregate reports.
  3. Ignore Cloudflare's "BIMI in use — fail" — BIMI is optional (needs `p=quarantine`+
     often a paid VMC cert); irrelevant to spam placement.

## Features

- [ ] **A/B test default prompt quality, starting with job preprocessing (extraction).**
  Idea (2026-07-27): our default prompts (`prompts/defaults/*.md`) were hand-written and
  never systematically evaluated — the skill_match false-positive bug is one symptom of
  this. Want to run structured A/B tests of prompt variants against real job/résumé data to
  measure and improve quality, starting with `extraction.md` (job description parsing,
  upstream of scoring/skill-match/generation — errors here cascade). User wants to try this
  as an agent loop (e.g. `/loop`): an agent generates prompt variants, runs them against a
  fixed job/profile eval set, scores results (accuracy, hallucination rate, or a rubric),
  and iterates. Needs: a frozen eval set (jobs + expected extraction fields), a scoring
  method (LLM-judge vs. deterministic diff vs. human spot-check), and a place to record
  variant results so improvements are traceable. Not started — needs its own
  spec/plan before implementation.

- [ ] **Railway log-drain docs.** Non-blocking follow-up from "Robust error logging for
  Railway (hosted)" (see Done) — document how to point Railway's log stream at an external
  log drain / query the JSON console lines, for anyone who wants search/alerting beyond the
  in-app admin Error Log viewer.

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

- [ ] **Gate the per-prompt user model override to admins only (platform-key path only).**
  _Scope narrowed 2026-11-16:_ BYOK users pay their own provider, so they may pick any model their
  key offers (`PUT /api/prompts` skips the allowlist for them); this item now only concerns users on
  the platform key. The model-override control on prompts should be admin-only for those users — regular users shouldn't pick their own model until
  tiered-model pricing is worked out (different models cost different credits). Revisit once
  pricing per model tier is designed (see the "High-effort toggle" item — same underlying
  cost-vs-quality knob). _Partially mitigated 2026-07-18:_ a server-side model allowlist
  (`LLM_ALLOWED_MODELS`; prod default = `LLM_DEFAULT_MODEL` only) now bounds what users can
  pick — see the audit entry in Done. The UI control + tier pricing question remains open.

- [ ] **Onboarding wizard for custom cover-letter (and other) prompts.** Idea (2026-08-12),
  from the `workflows/` local cover-letter prompt-tuning session: designing
  `workflows/prompts/cover_prompt.md` for personal use required a short interview (length/
  structure, thin-content handling, tone, enthusiasm framing) to translate vague preferences
  ("too long, I don't have much to say") into a concrete prompt. That question set is itself
  a reusable artifact — offer it to SaaS users as an onboarding step so they get a
  personalized cover-letter prompt/persona instead of one fixed house style. Likely the same
  pattern as the "Guided section-prompt authoring" item below (pre-formatted template vs.
  full GUI questionnaire); could share implementation. Not started — needs its own design
  pass on which questions to ask and how answers compile into a stored prompt override.

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

- [ ] **Remote MCP connector so Claude/ChatGPT subscribers can drive AutoApply from their own
  chat** (subscription OAuth in third-party apps is prohibited by Anthropic since Feb 2026, so
  "Sign in with Claude subscription" is off the table). Separate project; complements BYOK.

- [ ] **Self-serve account deletion/export.** The Privacy Policy currently tells users to email
  `barlowmatt96@gmail.com` to delete or export their data. Add an in-app "Export my data" (JSON
  of profile, jobs, documents, purchases) and "Delete my account" (account, identity,
  extension tokens, profile + all tenant rows, uploaded résumé files; keep purchase records
  only as long as tax rules require), then update `legal/Privacy.jsx`.

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
- [audit 2026-07-18] Prompt content is fully user-authored and runs on the platform key at flat
  unit prices (fixed-price LLM oracle). Accepted 2026-07-19: fine as long as worst-case output
  cost per call stays below the unit price (allowlisted cheap models keep this true — recheck
  if the allowlist ever adds a pricier model or max_tokens grows). BYOK users (2026-11-16) bypass
  this entirely — they run on their own key, unmetered, so the oracle only applies to the
  platform-key path.
- Stripe dashboard product names/descriptions may still mention pre-redenomination credit
  counts — check in the Stripe dashboard (app UI is authoritative).

## Done

- [x] **Security audit H3 + M1: unmetered-LLM audit, input caps, rate limiting, SSE cap.** **DONE
  2026-11-16** — every `get_client_for_profile` call site audited; the one tenant-reachable unmetered
  path (`Job.intake()` from `stage-job`/`scrape-selected`, a duplicate extraction + skill-match outside
  the metered `intake` bundle) removed. `core/limits.py` centralizes input caps (Pydantic 422 /
  `InputTooLarge` 413), `web/middleware_body_limit.py` caps raw bodies pre-parse, résumé upload reads
  in chunks. `web/middleware_rate_limit.py`: in-process token buckets (auth 30/min per IP, unsafe
  `/api/` 120/min per account, LLM/PDF routes 20/min), 429 + `Retry-After`, frontend toast. SSE
  streams capped at 5 per account, poll 50 ms → 250 ms. Limiter assumes a single Railway instance.

- [x] **Privacy Policy + Terms of Service pages.** **DONE 2026-11-16** — public `/privacy` and
  `/terms` SPA routes (`react-dashboard/src/components/legal/`, effective 16 Nov 2026), reachable
  logged out (auth gate only guards `/api/*`; `tests/web/test_legal_pages_public.py`). Linked from
  the landing footer, the sign-in card ("By signing in you agree…"), and the logged-in User home.
  Sign-in card copy also updated for open signups (the closed-beta message is gone).

- [x] **Buy me a coffee donation link.** **DONE 2026-11-16** — plain new-tab link to
  `https://buymeacoffee.com/mrbarlow` in the site footer and the User home ("AutoApply is free
  with your own API key…"). No BMC widget script, so the CSP is unchanged.

- [x] **Security audit hardening (H2, M3, L2, L3, L6, L7).** **DONE 2026-11-16** — fail-closed
  `APP_ENV` resolution via `core/env.py` (unknown value aborts boot; unset on Railway → production);
  `SecurityHeadersMiddleware` (nosniff, frame/referrer policy, prod HSTS, `'self'` CSP) + API docs
  hidden in production; `.dockerignore` excludes secrets/backups/DBs/dev dirs; auth gate rejects
  banned/missing accounts per request; admin flag re-synced from `ADMIN_EMAILS`/invites on login.
  Two deploy checks remain open under Bugs.

- [x] **Bring-your-own LLM key (BYOK).** **DONE 2026-11-16** (branch `feat/byok`) — accounts can
  store their own OpenRouter/OpenAI/Anthropic/Gemini key; BYOK usage is completely free (product
  decision), credits remain for users without a key. `core/secret_box.py` (Fernet, env
  `KEY_ENCRYPTION_KEY` — losing/rotating it makes stored keys unreadable, users re-enter),
  `core/byok.py` (providers, per-action credential contextvar, `list_text_models` doubles as key
  validation), `core/llm.py` resolution pinned BYOK → stored key → platform env (BYOK skips the
  model allowlist), `core/metering.py` never debits BYOK and pins the credential for the action.
  `Account` gains `llm_provider`/`llm_api_key_enc`/`llm_key_last4`/`llm_default_model` (migration
  `aa17byok01`, down_revision `aa16errdedup01`, new single head). `web/routers/llm_key.py`
  (`/api/account/llm-key`: GET/POST test/PUT/PATCH/GET models/DELETE; write-only key, 409 without
  an Account, 503 without the encryption key); `/api/me` gains `byok`; setup-status
  `llm_configured` counts a BYOK key; BYOK accounts may set any per-prompt model. Frontend
  `ApiKeySettings.jsx` (User home + collapsible onboarding panel), `CreditBalance.jsx` shows
  "Own API key · free". Tests: `tests/core/test_byok.py`, `tests/web/test_llm_key_api.py`,
  `ApiKeySettings.test.jsx`. **Deploy note:** set `KEY_ENCRYPTION_KEY` on Railway before users
  can save keys.

- [x] **`error_sink.py` dedup race + age-prune on bump-only steady state.** **DONE 2026-11-16**
  — `DbErrorHandler` replaced its SELECT-then-INSERT with an atomic dialect-aware upsert
  (`sqlalchemy.dialects.postgresql|sqlite.insert(...).on_conflict_do_update` on `fingerprint`,
  chosen from the session bind's dialect; refresh-on-dedup semantics unchanged, `RETURNING
  count` distinguishes insert from bump). Migration `aa16errdedup01` (down_revision
  `aa15errlog02`, new single head) collapses existing duplicate-fingerprint rows (sum `count`,
  min `created_at`, max `last_seen`, latest row's message/traceback/context) and makes
  `ix_error_events_fingerprint` UNIQUE; `ErrorEvent.fingerprint` declares `unique=True`. The
  `ERROR_LOG_MAX_AGE_DAYS` prune now also runs on dedup-bumps, time-gated to once per 10 min
  per process (module-level monotonic timestamp); row-cap prune stays insert-only. New tests
  in `tests/core/test_error_sink.py` (upsert increments, threaded same-fingerprint race → one
  row count 2, gated age-prune on bump) + `tests/db/test_error_dedup_migration.py`.

- [x] **Add ClaudeCliClient local LLM provider wrapper.** **DONE 2026-08-15**
  — commits `34ccc6b` (ClaudeCliClient implementation) + `6b984c9` (wire into LLM_PROVIDER_TYPE) + `3432212` (FileNotFoundError hardening).
  A dev-only local LLM backend for testing without OpenRouter: `core/llm_claude_cli.py`
  implements `ClaudeCliClient`, an OpenAI-SDK-shaped wrapper around the local `claude` CLI
  (runs `claude -p --output-format json` headless). Selected via `LLM_PROVIDER_TYPE=claude_cli`
  in `.env`; `core/llm.py` wires it into `get_client_for_profile()` and guards production
  access. Subprocesses single-turn (no tools), no cost tracking (cost=0), token counts from the
  CLI's JSON `usage` field. Raises `RuntimeError` if `claude_cli` is selected when
  `APP_ENV=production`; also raises `RuntimeError` with clear message when claude is not on PATH.
  Tests: `tests/core/test_llm_claude_cli.py` (7 tests) +
  `tests/core/test_llm.py` (3 new tests for provider selection + guard + error message).

- [x] **Tighten `skill_match` prompt to require real evidence for concrete techs.** **DONE
  2026-07-27** — friend testing the app hit false-positive skill matches: a résumé with no
  Skills section still got required skills marked as satisfied, because `skill_match.md`
  told the LLM to be generous about "implied" requirements without distinguishing concrete
  named technologies from broad/generic ones. Rewrote `prompts/defaults/skill_match.md` so
  the generosity clause applies only to broad/generic requirements; any concrete
  tech/framework/tool/platform must be explicitly named or unambiguously entailed in the
  candidate's skills/work-history/projects/education, with an explicit "empty skills list is
  not license to infer from vague experience" instruction. Local dev `PromptDefault` row
  updated directly (seed is idempotent — editing the file alone doesn't reach existing rows).
  **Live Railway DB NOT reseeded** — needs explicit approval per the manual-reseed policy in
  `core/CONTEXT.md`. Confirmed the "give every profile a default hidden Skills section +
  let users mark a skill chip as owned" idea was already fully built (`legacy_to_tree`
  always creates a Skills section even when empty; `visible` flag + empty-section-omission
  already hide it until populated; `SkillChipModal.jsx` → `addProfileSkill`/
  `removeProfileSkill` already wires the chip-click "a skill I have" toggle) — no code
  change needed there.

- [x] **Error observability hardening.** **DONE, MERGED & PUSHED 2026-07-24** — merge commit
  `667a7ec` (branch `worktree-error-observability`, now deleted). 6-task follow-up on top of
  "Robust error logging for Railway" (below): `fingerprint()` normalizes hex addresses/UUIDs/
  quoted literals/integers while preserving standalone 3-digit codes (404/500 stay distinct);
  dedup refreshes traceback/message on bump, `_prune` runs only on insert; new `method` +
  `account_email` fields flow request → context bag → `JsonFormatter` → `error_events`
  (migration `aa15errlog02`, down_revision `aa14errlog01`, now the single alembic head;
  `_resolve_profile_id` renamed `_resolve_identity`); admin API + `ErrorLog.jsx` surface both
  (Method column, `email (#id)` identity cell); dev/console `_FMT` gained `[request_id method
  route]`, rotating file handler now has its own `ContextFilter`. 972 core+web tests pass.
  Non-blocking follow-ups: SELECT-then-INSERT dedup race + age-prune on bump-only steady
  state (both DONE 2026-11-16), `account_email` PII-at-rest (still under Bugs).

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

- [x] **Assign unique field keys for multi-column parsed list sections (2nd parse/apply 422 fix).**
  **DONE 2026-07-27** — commit `f8112dd`. A live user's multi-column "list"-kind extra section
  (custom Role/Date/Description columns, e.g. "Leadership Activities") left every `FieldNode` key
  defaulted to `""`; `validate_tree` rejects sibling `FieldNode`s sharing a key, 422ing parse/apply.
  Distinct from the `order` bug above (same function, different `validate_tree` invariant). Fixed
  in `core/parsed_sections.py`'s `build_section_from_parsed` ("list" and "fields" kind branches) by
  passing explicit `key=` to each `FieldNode()`.

- [x] **Robust error logging for Railway (hosted).** **DONE 2026-07-23** — all 8 tasks
  merged. The local rotating-file logging
  (`core/logging_config.py`, "Structured error logging v1") doesn't help on Railway — the `/data`
  volume log file isn't easily inspectable and container restarts/redeploys scatter context. Built
  hosted-grade error observability: tracebacks/`logger.exception` output now reaches Railway's
  log stream (stdout/stderr JSON so it's queryable in the Railway logs UI), structured (JSON) vs.
  plain formatting is selected per env, and the deferred v2 from error-logging-v1 — a queryable
  DB error table + in-app admin viewer — is shipped, so production failures are diagnosable
  without SSHing into the container.
  **Task 1** — commit `3d069e9`: new `core/log_context.py`, a contextvars-backed
  log context bag (`bind()`/`clear()`/`snapshot()` for request_id/route/profile_id) +
  `ContextFilter` (injects those fields onto every `LogRecord`). Self-contained; not yet wired
  in. **Task 2** — commit `b81a83e`: `core/logging_config.py` gained
  `JsonFormatter` (single-line JSON: `ts, level, logger, msg, route, profile_id, request_id`,
  plus rendered `exc_info` traceback when present) and `_console_formatter()`, which selects
  `JsonFormatter()` when `APP_ENV=production` else the existing plain formatter. The console
  handler now uses `_console_formatter()` and has `ContextFilter` attached, so route/profile_id/
  request_id populate whenever they're bound. The rotating file handler is unchanged (still
  plain-text). Tests in `tests/core/test_json_formatter.py` (6/6 passing). **Task 3**
  — commit `dc0bdd5`: new `web/middleware_request_context.py`
  (`RequestContextMiddleware(BaseHTTPMiddleware)`) calls `log_context.bind(request_id, route,
  profile_id)` at the start of every request (`request_id` a fresh uuid4 hex; `route` the request
  path; `profile_id` best-effort-resolved from `request.session["account_id"]` →
  `db.database.Account.profile_id` via a throwaway `SessionLocal()`, swallowing any error to
  `None`), sets an `X-Request-ID` response header, and clears the context in a `finally` block.
  Wired in `web/main.py` via `app.add_middleware(RequestContextMiddleware)` right after
  `ImpersonationReadOnlyMiddleware` and before `SessionMiddleware` (which must stay outermost/
  last-added). Tests in `tests/web/test_request_context_mw.py` (2/2 passing); full `tests/web`
  suite (404 tests) green. Starlette 0.49.3 — the documented contextvar-propagation risk across
  `BaseHTTPMiddleware`'s task boundary did not manifest. **Task 6** — commit
  `bdc8e42`: Alembic migration `aa14errlog01` adds the global `error_events` table
  (`db.database.ErrorEvent`) — admin-only, deliberately **not** tenant-scoped/excluded from
  `_TENANT_TABLES` (see `db/CONTEXT.md`). Tests in `tests/core/test_error_events_model.py`.
  **Task 4** — commit
  `33de040`: new `core/error_sink.py` — `fingerprint(record)` (sha1 dedup key: logger + exception
  type + normalized top frame, or logger+message when no `exc_info`), `DbErrorHandler`
  (`logging.Handler` that upserts into `db.database.ErrorEvent` by fingerprint — increments
  count/bumps last_seen on an existing row else inserts; uses its own short-lived `SessionLocal()`
  session; prunes rows older than `ERROR_LOG_MAX_AGE_DAYS` (default 30) and caps total rows at
  `ERROR_LOG_MAX_ROWS` (default 1000); `emit()` swallows all exceptions so logging can never
  cascade-fail), and `install_db_error_handler(root)` (attaches the handler at ERROR level unless
  env var `ERROR_LOG_DB` disables it). `core/logging_config.py`'s `setup_logging()` now calls it
  near the end, wrapped in try/except. Tests in `tests/core/test_error_sink.py` (5/5 passing:
  insert, dedup+increment, prune-by-max-rows, exception-swallowing, fingerprint stability across
  line numbers). **Task 5** — commit `135eff2`: `web/main.py` gained a global
  `@app.exception_handler(Exception)` (`_log_unhandled_exception`, module logger
  `web.unhandled`) registered above the existing `InsufficientCredits` handler — it calls
  `logger.exception(...)` with the request path, then re-raises so Starlette's standard 500
  response is unaffected. This routes every unhandled exception through the Task 3 request-context
  fields, the Task 2 JSON console formatter, and the Task 4 DB error sink, without changing
  client-visible behavior. Test in `tests/web/test_unhandled_exception_logged.py`; full
  `tests/web` suite (405 tests) green. **Task 7** — commit `d74f8f6`: admin
  `error_events` API — `GET /api/admin/errors` (filters: `level`/`route`/`profile_id`/`since`),
  `GET /api/admin/errors/{id}` (detail incl. traceback/request_id), `DELETE /api/admin/errors`
  (clear all) — admin-gated, in `web/routers/admin.py`. **Task 8** — commit
  `f0b8784`: frontend admin panel — `react-dashboard/src/api.js` gained `getErrors(params)`/
  `getErrorDetail(id)`/`clearErrors()`; new `react-dashboard/src/components/admin/ErrorLog.jsx`
  (filter bar, grouped/expandable error table, "Clear all"), wired into `AdminPage.jsx` as a new
  `errors` nav entry. Tests in `ErrorLog.test.jsx`. Non-blocking follow-up (Railway
  log-drain docs) tracked as its own Features item.

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

