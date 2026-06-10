# TODO

Backlog for multi-session work. Update this file whenever scope changes or an item is completed:
mark items `[x]`, move them to **Done**, or revise scope notes inline.

## Bugs

_(none)_

## Features

### Hosting / SaaS conversion

- [ ] **Multi-tenancy rework** — Convert the single-user local app to a multi-tenant system.
  SQLite → Postgres (with Alembic migrations, replacing `init_db.py`); add `profile_id` to every
  tenant-scoped table (`jobs`, `documents`, per-tenant `config`, skill aliases) and filter every
  query in `core/` + `web/routers/` by the active tenant via a `current_profile_id` seam; decouple
  the tray app into an optional local client that authenticates to the hosted API with a token.
  Design: `docs/superpowers/specs/2026-06-10-multi-tenancy-rework-design.md`. **Gates everything
  below — do this first.**

- [ ] **Auth** — Per-user identity filling the `current_profile_id` seam. Use a managed provider
  (Clerk / Auth0 / Supabase Auth) rather than hand-rolling; gives OAuth, sessions, password reset,
  email verification. Depends on multi-tenancy.

- [ ] **Hosting (PaaS)** — Deploy API + React dashboard to Railway or Render with managed Postgres
  and env-var secrets; push-to-deploy. Tray app stays local. Depends on multi-tenancy + auth.

- [ ] **Usage-credit payments** — Credit ledger table (grants/debits/balance per tenant); meter LLM
  call sites in `core/job.py` (score/generate/refine cost credits); Stripe Checkout for credit-pack
  purchases + webhooks to grant credits; enforce by blocking generation at zero balance. Depends on
  hosting + auth. Ledger design needs its own brainstorm pass.

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
