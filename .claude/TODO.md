# TODO

Backlog for multi-session work. Update this file whenever scope changes or an item is completed:
mark items `[x]`, move them to **Done**, or revise scope notes inline. Prune stale done entries —
git history is the archive (see `.claude/skills/update-todo/`).

## Bugs

- [ ] **Follow-ups for email deliverability (non-blocking).**
  1. **Verify auth in practice:** send a real invite to Gmail → "Show original" → confirm
     SPF/DKIM/DMARC all say PASS. Beats the Cloudflare dashboard widget (report-driven,
     24–72h lag; empty/stale until traffic flows).
  2. **Tighten DMARC to `p=quarantine`** after ~a week of clean aggregate reports.
  3. Ignore Cloudflare's "BIMI in use — fail" — BIMI is optional (needs `p=quarantine`+
     often a paid VMC cert); irrelevant to spam placement.

## Features

- [ ] **Full automation of document submission**for personal tool use only. Fill in all the ATS 
  tickers. For non easy apply jobs, so that we can avoid LinkedIn native bot detection.

- [ ] **Gate the per-prompt user model override to admins only.** The model-override control on
  prompts should be admin-only for now — regular users shouldn't pick their own model until
  tiered-model pricing is worked out (different models cost different credits). Revisit once
  pricing per model tier is designed (see the "High-effort toggle" item — same underlying
  cost-vs-quality knob).

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
- Stripe dashboard product names/descriptions may still mention pre-redenomination credit
  counts — check in the Stripe dashboard (app UI is authoritative).

## Done

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
