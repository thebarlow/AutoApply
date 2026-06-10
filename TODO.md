# TODO

Backlog for multi-session work. Update this file whenever scope changes or an item is completed:
mark items `[x]`, move them to **Done**, or revise scope notes inline.

## Bugs

_(none)_

## Features

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
