# 4C — ATS gate rework (Profile Schema Engine #4C)

**Date:** 2026-06-23
**Status:** Design approved, spec under review
**Parent:** Profile Schema Engine #4 (full tree swap) → 4C
**Prior:** 4B-1 (tree-v1 in production) + 4B-2 (per-section refinement)
**Release constraint:** merges to LOCAL `main` only — do NOT push `main` until the whole swap (#4–#6 and #5) is complete.

## Problem

The mechanical ATS layer (`core/ats_gate.check_mechanical`) was written against the
fixed 5-section typed `ResumeDocument`. It hard-blocks the **applied** transition when a
section heading from `doc.section_order` is not found verbatim in the extracted PDF text
(`section_missing`, severity `critical`). With the tree swap, sections are now
user-defined: a fresher or career-changer may legitimately have no "Experience" section,
and section names are arbitrary. A required-fixed-heading rule with literal matching is
therefore both wrong (no section is universally required) and brittle (literal heading
text need not survive extraction even when the résumé is perfectly parseable).

4C removes that hard-block and its literal heading matching, drops the small skill
synonym map (vendor synonym dictionaries are proprietary and out of scope), and moves
section-structure verification to the **advisory** semantic roundtrip, which is
non-blocking by construction.

## Scope

- **In:** `core/ats_gate.py` mechanical + roundtrip layers; the tree→gate adapter
  (`core/ats_tree_adapter.py`) only insofar as `section_order` changes consumer.
- **Out / unchanged:**
  - The blocking contract: **critical** mechanical issues still hard-block the applied
    transition; warnings never block. (`AtsReport.build`, the confirm-applied gate.)
  - `no_text_layer`, `contact_missing`, `contact_order`, `present_skill_dropped`,
    `glyph_junk` mechanical checks (kept; see Decisions for the literal-matching change to
    `present_skill_dropped`).
  - `run_ats_check` wiring, PDF extraction, report storage, score formula.
  - Legacy `ResumeDocument` résumé rows: the same gate runs over them; behavior changes
    identically (no section hard-block) — acceptable and intended (the fixed-heading rule
    was never desirable).

## Decisions (from brainstorming)

- **`section_missing` (mechanical, critical):** **deleted entirely.** No mechanical
  heading check remains — neither blocking nor advisory at the mechanical layer.
- **Semantic roundtrip:** **extended** with an advisory section diff. The roundtrip
  already asks the LLM to parse `sections` from the extracted text; 4C compares that
  against the document's visible section names and emits a **warning-only**
  `roundtrip_sections` issue when document sections are missing from the parse. This
  picks up the structural-survival signal the deleted literal check used to give, without
  blocking and without requiring any fixed heading.
- **Skill synonym map:** **removed.** Delete `_RAW_SYNONYMS` / `_SKILL_SYNONYMS`;
  `present_skill_dropped` matching becomes pure case-insensitive literal substring. It is
  warning-only, so the extra false warnings this may produce (e.g. "Postgres" vs
  "PostgreSQL") never block an application.
- **`section_order` on the adapter:** **kept**, but its consumer moves from the mechanical
  layer to the roundtrip. `resume_document_for_ats` still projects visible section names
  (now used only by `check_roundtrip`).

## Components

### 1. `check_mechanical` (`core/ats_gate.py`)

- Remove the `# section_missing` block (the `for section in doc.section_order:` loop) in
  full.
- Simplify `_present` to literal-only:
  ```python
  def _present(term: str, haystack_lower: str) -> bool:
      """Case-insensitive literal substring match."""
      t = term.strip().lower()
      return bool(t) and t in haystack_lower
  ```
- Delete `_RAW_SYNONYMS` and `_SKILL_SYNONYMS`.
- `no_text_layer`, `contact_missing`, `contact_order`, `present_skill_dropped`,
  `glyph_junk` are otherwise untouched. The `doc` parameter is still required (header
  fields); the signature does not change.

### 2. `check_roundtrip` (`core/ats_gate.py`)

After the existing name/email/phone comparisons, add an advisory section diff:

- Build the document's expected section set: `{s.strip().lower() for s in
  doc.section_order if s.strip()}`.
- Build the parsed set: `{s.strip().lower() for s in parsed.sections if s.strip()}`.
- `missing = [s for s in doc.section_order if s.strip() and s.strip().lower() not in
  parsed_set]` (preserve document order in the message).
- If `missing` is non-empty **and** `parsed.sections` is non-empty (an empty parse means
  the LLM returned nothing useful — do not fabricate a finding), append one
  `AtsIssue(layer="semantic", severity="warning", code="roundtrip_sections",
  message="Parser did not recover section(s): <comma-joined missing>.")`.
- All existing roundtrip guarantees hold: any LLM/parse failure already returns `[]`
  before this point; the new check never raises and never produces a critical.

### 3. Adapter (`core/ats_tree_adapter.py`)

No functional change required — `resume_document_for_ats` keeps projecting `section_order`
(now consumed by the roundtrip instead of the mechanical layer). Update its module
docstring to reflect that `section_order` feeds the semantic roundtrip, not a mechanical
hard-block.

## Data flow (unchanged except issue set)

`run_ats_check` → `extract_text` → `run_gate(pt, doc, …)` →
`check_mechanical` (now: no `section_missing`, literal-only skill match) +
`check_roundtrip` (now: + advisory `roundtrip_sections`) → `AtsReport.build`
(critical → `passed=False`). Score formula unchanged
(`1 − 0.25·crit − 0.05·warn`, clamped).

## Error handling

- Roundtrip remains fully advisory: the section diff runs only after a successful parse;
  on any exception the function returns `[]` as today.
- An empty parsed-sections list suppresses the new warning (avoids a spurious finding when
  the LLM under-parses).
- Mechanical layer behavior on `no_text_layer` (early return) is unchanged.

## Back-compat

- Tree-v1 and legacy `ResumeDocument` rows both lose the `section_missing` hard-block and
  the synonym-aware skill match. No data migration; no schema change.
- `AtsIssue` / `AtsReport` schemas unchanged (new `code` value `roundtrip_sections` is a
  free-form string; no enum to extend).
- `ats_parse` prompt unchanged (already returns `sections`).

## Testing

- **Mechanical — section drop:** a `ResumeDocument` with `section_order=["experience",
  "skills"]` whose headings are **absent** from the extracted text now yields **no**
  critical issue (was `section_missing`). Assert no issue has `code="section_missing"`.
- **Mechanical — kept checks still fire:** `no_text_layer`, `contact_missing`,
  `contact_order` critical cases from `tests/core/test_ats_mechanical.py` still produce
  their criticals (regression guard — update the section-missing test to assert absence).
- **Synonym removal:** a résumé text containing "postgres" with a wanted/owned skill
  "postgresql" now emits a `present_skill_dropped` warning (literal miss), proving the map
  is gone. A literal match ("postgresql" present) emits nothing.
- **Roundtrip — section diff:** stub the LLM parse to return `sections=["experience"]`
  against `doc.section_order=["experience","skills"]` → one warning-only
  `roundtrip_sections` naming "skills". With `sections=[]` → no `roundtrip_sections`
  issue. With all document sections present → none. Assert severity is always `warning`
  (never blocks).
- **run_gate integration:** a clean PDF + matching doc with arbitrary custom section names
  produces `passed=True` and no `section_missing`.

## Out of scope

- Roles / per-section ATS rules; any synonym or vendor-dictionary matching.
- ATS scoring-weight changes; the score formula stays.
- DocumentModal / feedback-refine (4D); user-formatted PDF (#6); onboarding parse (#5).
- Any change to the blocking contract or the confirm-applied endpoint.
