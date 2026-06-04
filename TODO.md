# TODO

Backlog for multi-session work. Update this file whenever scope changes or an item is completed:
mark items `[x]`, move them to **Done**, or revise scope notes inline.

## Bugs

_(none)_

## Features

- [ ] **Document user feedback** — Let the user give feedback on a generated document (resume/cover
  letter) that feeds back into regeneration.

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
