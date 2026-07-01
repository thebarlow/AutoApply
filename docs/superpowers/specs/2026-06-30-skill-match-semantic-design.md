# Semantic required/preferred skill matching — design

**Date:** 2026-06-30
**Status:** approved, pending implementation plan

## Problem

On the job extraction view, required/preferred skill chips are colored
have/missing by `POST /api/skills/owned`, which marks a chip "have" only when
its normalized `skill_key` is **literally equal** to a key in `user.skills`
(case- and alias-aware, but no semantic reasoning). Two failure modes observed
on live job `indeed_1782853202166`:

1. **Noisy extraction.** `required_skills` contains non-skills: credentials
   ("Bachelors degree"), job titles ("Software Engineer or Programmer",
   "Coder"), and generic filler ("Proficiency in one programming language").
   These can never literally match and clutter the panel.
2. **No semantic matching.** Legitimate items the candidate satisfies via
   evidence outside the skills list — education (a degree), work history (past
   titles), or implied soft skills ("Fluency in English") — are marked missing
   because matching only consults `user.skills` with literal equality.

## Goals

- Stop the extractor emitting credentials, job titles, and generic phrases as
  skills.
- Mark a chip "have" when the **full profile** (skills + education + work
  history + projects) satisfies it, not just a literal skills-list token.
- Keep render-time cost at zero: compute the semantic match once and cache it.
- Keep the "A skill I have" click flow and profile edits reflecting instantly
  where possible; give the user an explicit re-check for the rest.

## Non-goals

- No automatic re-run of the semantic match on every profile edit (too costly
  across all jobs).
- No change to the scoring axes or the ATS gate.

## Design

### Part A — Extraction cleanup (prompt only)

Edit `prompts/defaults/extraction.md` to define what belongs in
`required_skills` / `preferred_skills`: a concrete technology, tool,
methodology, or competency. Instruct the extractor to **exclude**:

- Credentials / degrees ("Bachelors degree").
- Job/role titles ("Software Engineer or Programmer", "Coder").
- Generic filler ("Proficiency in one programming language" → emit the named
  language if the JD names one, else drop).

This is a DB-backed prompt: `prompts/defaults/extraction.md` is the seed. The
live/local active prompt row must be updated separately (re-seed or edit the
`prompts` row for the active profile). Flag this in the plan as a manual step.

### Part B — Semantic match at extract-time, cached

1. **Schema/model:** new nullable column `ext_skill_match` (JSON, stored as
   Text like the other `ext_*` fields) on the `jobs` table. Holds the list of
   chip strings the LLM judged satisfied, plus a `match_hash` of the profile
   skill set used (see Part D). Store as a small JSON object, e.g.
   `{"matched": [...], "profile_hash": "..."}`. Alembic migration +
   `db/database.py` model update + `init_db.py` idempotent path.
2. **Prompt + schema:** new `skill_match` prompt (`prompts/defaults/skill_match.md`
   + DB seed) and a `SkillMatchResponse` Pydantic model in `core/schemas.py`
   (`matched: list[str]` — echoes back the satisfied input chip strings).
3. **Matcher:** in `core/job.py`, after `extract_description` sets the skill
   fields, run one LLM call sending the full profile and the combined
   required + preferred + tech chip list, asking which the candidate satisfies.
   Persist the satisfied subset + profile hash to `ext_skill_match`. Reuse the
   existing `ext_seniority` idempotency guard so it is not re-run needlessly.
   Attribute cost via the existing `session_cost` path.

### Part C — Serve the merged result

`POST /api/skills/owned` gains an optional `job_key`. A chip is "have" if
**either**:

- the live literal/alias match (current logic — so profile edits and the
  "A skill I have" toggle update instantly), **or**
- it appears in that job's cached `ext_skill_match.matched`.

`ExtractionView` passes `job_key` (available on the job `data`). The response
still echoes the original input strings so the component maps results onto its
chips unchanged.

### Part D — Handling profile changes after extraction

- **Click a chip → "A skill I have"** (`SkillChipModal`): `addProfileSkill`
  inserts the chip's exact canonical string into `user.skills`, so the live
  literal layer flips it to "have" immediately. No LLM, no extra work. Fully
  covered.
- **Add a skill via the profile modal** that only *semantically* satisfies a
  still-missing chip: covered by a **manual re-check button** (↻) on the job's
  skill panel in `ExtractionView`. Clicking it re-runs the semantic matcher for
  that one job and re-caches `ext_skill_match`. New endpoint, e.g.
  `POST /api/jobs/{job_key}/rematch-skills`. Cost is explicit and per-job.
- `profile_hash` on the cache lets the button (and future logic) detect whether
  the cache predates the current profile skill set; the button may show a
  subtle "stale" affordance when hashes differ. (Affordance optional; the
  button always works regardless.)

### Part E — Backfill

One-off script (mirroring `flag_failed_scrapes`) that iterates already-extracted
jobs, runs the semantic matcher, and populates `ext_skill_match`. Lets the cited
live job get semantic matches without re-scraping. Idempotent; skips jobs with
no extracted skills.

## Testing

- `SkillMatchResponse` parse path via `parse_llm_json` with a mocked response.
- Prompt-fill for `skill_match` (profile fields interpolated correctly).
- Merged `/owned` logic: literal-only, cache-only, and union cases; unknown
  `job_key` degrades to literal-only.
- Extraction-cleanup regression: mocked extraction response asserting non-skill
  items are excluded through the storage path (`ext_required_skills`).
- Re-match endpoint: recomputes and updates the cache for one job.
- Backfill script: populates cache, skips skill-less jobs, is idempotent.

## Open risks

- Cache reflects the profile at match time; profile-modal semantic additions
  need the manual re-check to surface (by design).
- Extraction-cleanup quality depends on prompt adherence; the regression test
  guards the storage path, not model judgment.
