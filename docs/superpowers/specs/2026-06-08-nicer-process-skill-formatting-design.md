# Nicer process/skill formatting — Design

**Date:** 2026-06-08
**Scope:** The processed/extracted job description ("Description" tab). Two levers: the
`ExtractionView` UI rendering and the `extraction` LLM prompt. No other surface
(résumé/cover output, score rationale) is in scope.

## Goal

Make the processed description read denser and cleaner: more tables, fewer bullet
points, less prose. Condense skill/responsibility phrasing at the source so the LLM
emits terse tokens ("Strong proficiency in Python" → "Python"; "Hands-on experience
with LLMs and generative AI" → "LLMs", "generative AI").

## Part A — Prompt (`prompts/defaults/extraction.md`)

Add condensing directives to the Instructions section:

- `required_skills` / `preferred_skills` / `tech_stack`: bare canonical tokens only.
  Strip qualifiers ("Strong proficiency in", "Hands-on experience with",
  "Deep knowledge of"). Split conjoined phrases into separate entries
  ("LLMs and generative AI" → two entries).
- `key_responsibilities`: ≤6 words each, no leading filler verbs/adjectives.
- `company_signals`: ≤5 words each, terse cue phrases.

Schema and key set are unchanged — only the phrasing guidance changes.

### Reseed: `extraction_prompt_v2` gate (only-if-unmodified)

DB-backed prompts only seed missing rows, so the new default must be propagated by a
gated migration in `db/database.py`, registered alongside the existing
`_migrate_resume_*_prompt_v2` calls.

`_migrate_extraction_prompt_v2()`, gated by Config key `extraction_prompt_v2`:

1. If the gate flag is `"1"`, return.
2. Read new content from `prompts/defaults/extraction.md`.
3. Capture the **old** default content from the `PromptDefault` row (`type_key="extraction"`).
4. Update each profile `Prompt` row with `type_key="extraction"` **only if** its content
   equals the old default (i.e. the user never edited it). User-edited prompts are preserved.
5. Set the `PromptDefault` row content to the new content (create if missing).
6. Set the gate flag to `"1"`; commit.

Edge case: if there is no existing `PromptDefault` row (fresh install), step 3's "old
content" is empty; no profile rows match empty, so only the default is seeded — correct.

## Part B — UI (`ExtractionView` in `react-dashboard/src/components/widgets/Settings.jsx`)

Three rendering regions:

1. **Meta** (seniority, role_type, domain, work_arrangement, employment_type) — replace
   the `·`-joined prose line with a compact 2-column key→value table. Only include keys
   with non-empty values. Labels: Seniority, Role, Domain, Arrangement, Type.

2. **Chip groups** (required_skills, preferred_skills, tech_stack) — unchanged. Already
   condensed chips; keep the 3-state ownership coloring, `✓`, the `SkillChipModal` wiring,
   and the legend.

3. **Bullet groups** — split the two:
   - `key_responsibilities` → borderless tight-row table (no `list-disc`): each phrase on
     its own row, dense vertical rhythm. Reuse the meta table's row styling.
   - `company_signals` → chips (neutral styling; not clickable / no ownership — these are
     not skills, so do **not** wire them to `SkillChipModal` or the owned-set fetch).

Owned-set logic (`getOwnedSkills`, `allSkills`) stays scoped to the three chip groups only.

## Testing

- **Prompt migration** (`tests/db/`): mirror `test_resume_eval_prompt_migration.py`.
  - Unmodified profile prompt → updated to new content; gate flag set to `"1"`.
  - User-edited profile prompt (content ≠ old default) → preserved.
  - Second run is a no-op (idempotent).
  - Default row updated to new content.
- **UI**: no existing component test harness for Settings; verify by running the app and
  inspecting the Description tab (meta table, responsibilities table, signal chips).

## Out of scope

Résumé/cover generation phrasing, score rationale, chip ownership for company_signals,
schema/key changes.
