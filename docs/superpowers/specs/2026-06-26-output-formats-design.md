# Output formats (#6B-1)

**Date:** 2026-06-26
**Status:** Design approved
**Sub-project:** Profile Schema Engine #6, phase 6B-1 (output formats). Document-level
themes are #6B-2, a separate later spec.
**Release constraint:** merges to LOCAL `main` only — do NOT push `main` until the whole
Profile Schema Engine swap (#4 → #6 → #5) is complete.

## Problem

Today, how a résumé section's body renders (bullets vs. flowing prose) is whatever the LLM
happened to emit as freeform markdown into a `markdown`-kind field. There is no way for a
user to choose, per section/item, that Experience should be bullet points while a Summary is
a paragraph — and because the body is freeform markdown, the output is not structurally
guaranteed.

This sub-project introduces **output formats**: named, preconfigured descriptors attached to
each LLM-authored prose field. A format simultaneously (a) instructs the LLM to return a
specific JSON shape and (b) tells the renderer how to lay that structure out. The user picks a
format (or inherits it from the section/item template they added); they never author the
underlying instruction. This guarantees structured, readable data and gives deterministic
rendering.

## Decisions (from brainstorming)

- **Scope:** output formats only. Document-level CSS themes are #6B-2.
- **Storage scope:** profile-level — the format lives on the field in the profile tree (the
  source of truth), like the section schema and `resume_max_pages`. No per-job override.
- **Granularity:** per LLM-authored prose field, defaulted by the section/item template. List
  items are cloned from the item template, so all entries share the template's format by
  default, while a user *could* set one field differently. No separate inheritance machinery.
- **Generation-coupled:** the format injects an instruction into the LLM call (an
  "# Output Format" block) so the model authors the right shape, and drives rendering. Both
  layers, kept in sync by one descriptor.
- **Structured JSON:** each format declares the JSON shape the LLM returns; the response is
  validated/coerced per field before storage. No freeform-markdown parsing.
- **Format is the driver:** a field references an `output_format`; the registry maps it to a
  storage `kind` + render behavior + LLM shape instruction. Adding a new format later is one
  registry entry, no new `kind`.
- **Initial set: two formats** — Bullet list, Paragraph — with template defaults chosen so
  existing résumés render unchanged.
- **Tree-v1 résumé only.** The legacy `ResumeGeneration` whole-résumé path and cover letters
  are untouched.

## Architecture

Pipeline today: document tree → `core/tree_assembler.py` (role-dispatched markdown) → pandoc →
HTML+CSS → Chromium PDF. Generation: `core/section_generator.py` makes one structured-JSON LLM
call per section (`SectionOutput.fields: dict[str, str | list[str]]`), baked into the tree by
`core/document_tree.py`. Output formats add a descriptor consulted in both the generation and
assembly steps.

### Unit 1 — Output format registry (`core/output_formats.py`, new)

A pure module, no DB/LLM/filesystem. Defines an `OutputFormat` descriptor and a fixed registry
keyed by id. Each entry carries:

- `id: str` — e.g. `"bullets"`, `"paragraph"`.
- `label: str` — e.g. "Bullet list", "Paragraph".
- `kind: Literal["bullets", "markdown"]` — the `FieldNode.kind` this format aligns to; the
  existing `FieldNode` value normalizer coerces the stored value accordingly (`bullets` →
  `list[str]`, `markdown` → `str`).
- `prompt_shape: str` — the per-field instruction text for the prompt's "# Output Format"
  block. Gist:
  - **bullets:** "an array of concise bullet strings, one achievement each, max 2, each ≤120
    characters."
  - **paragraph:** "a single flowing paragraph string, no bullet points."

Public helpers: `get_format(id) -> OutputFormat | None`, `all_formats() -> list[OutputFormat]`,
and a default-id constant. Single responsibility: hold the format definitions and look them up.

### Unit 2 — Schema attribute (`core/profile_tree.py`)

Add `output_format: str = ""` to `FieldNode`. When non-empty and present in the registry, the
registry entry is authoritative and the field's `kind` is aligned to the format's `kind`
(set at construction in the presets and on format change in the editor). Empty `output_format`
= today's behavior (back-compat; no coercion). The vestigial unused `ListNode.bullet_style`
may be left as-is (out of scope) — do not build on it.

Defaults are set in `core/section_presets.py`:
- Experience item body (`summary`) → `bullets` (kind `bullets`).
- Summary `hero` → `paragraph` (kind `markdown`).
- Project `description` → `paragraph` (kind `markdown`).

Skills (taglist) and Header are not prose fields and carry no `output_format`.

### Unit 3 — Generation wiring (`core/section_generator.py`)

When building a section prompt, append an **"# Output Format"** block that lists each
authored (outputable, unlocked) field by key with its format's `prompt_shape`. Fields with no
`output_format` keep their current spec line unchanged. After the `SectionOutput` response
returns, **validate/coerce each authored field's value to its format's expected type** before
baking it into the tree: a `bullets`-format field must end up a `list[str]` (a returned string
is split/wrapped), a `paragraph`-format field must be a `str` (a returned list is joined). The
sectioned eval/refine loop (`Job.evaluate_resume_sections` / `_run_resume_section_refinement`)
reuses this generator, so formats apply identically on refine.

### Unit 4 — Rendering (`core/tree_assembler.py`)

Render the authored body by its stored structure: a `list[str]` renders as a `- ` bullet list;
a `str` renders as a prose paragraph. The experience formatter stops emitting the raw body
string and renders the structured value through the shared field renderer. Output is
deterministic from the stored value; no markdown re-parsing.

### Unit 5 — UI (`react-dashboard/src/components/widgets/profile-tree/`)

A small format `<select>` on each LLM-authored prose field, options from the registry (exposed
via a tiny backend endpoint or a bundled constant — implementer's choice in the plan, prefer a
backend endpoint so the registry stays single-source). Changing it persists the field's
`output_format` (and aligned `kind`) through the existing whole-tree `PUT`. Section/item
templates carry defaults, so users typically never touch it. No DocumentModal changes.

### Unit 6 — Migration / backfill (`scripts/`)

Existing profiles store Experience `summary` as a `markdown` **string** of bullet text.
Setting its format to `bullets` (→ `list[str]`) requires a one-time, idempotent backfill that
splits that string on bullet lines (`- ` / newlines) into an array and sets the
`output_format`/`kind`; otherwise the value normalizer collapses the multi-bullet string into a
single bullet. Same pattern as the section-prompt backfill: load each stored `profile_tree`,
fill only fields matching the known default roles whose `output_format` is unset, write back,
report counts. **Take a DB backup before running.** Profiles without the attribute keep working
via the empty-default path. A pure helper (`backfill_output_formats(root) -> bool`) does the
tree mutation; the script wraps it over the DB.

## Error handling

- A field's `output_format` not in the registry → treat as unset (current behavior); never
  crash a render or a prompt build.
- A generation response whose field value is the wrong type for its format → coerce per the
  format's `kind` (split string→list / join list→string); never drop the field.
- Backfill on a field already migrated (has `output_format`) → no-op (idempotent).
- A list section with no items, or a prose field with empty value → renders empty, no crash.

## Testing

- **Registry (`tests/core/`):** `get_format` lookups, `all_formats`, the format→kind alignment.
- **Generator:** the prompt includes an "# Output Format" block naming each authored field's
  shape; a `bullets`-format field coerces to `list[str]`; a `paragraph`-format field coerces to
  `str`; a wrong-typed response is coerced, not dropped.
- **Assembler:** a `list[str]` body renders as a `- ` list; a string body renders as a
  paragraph; a default tree whose formats match today's behavior renders byte-equivalent where
  applicable.
- **Backfill:** a markdown bullet string splits into the expected array; idempotent on a second
  run; a non-bullet paragraph string is preserved; user-set formats are never overwritten.
- **Frontend (Vitest + RTL):** the format `<select>` renders the registry options, shows the
  field's current/default format, and persists a change through the tree PUT.

## Out of scope

- Document-level CSS themes — #6B-2.
- Per-item override UI beyond the per-field `<select>`.
- Cover letters and the legacy `ResumeGeneration` whole-résumé generator.
- New formats beyond Bullet list and Paragraph (the registry is built to extend, but only two
  ship now).
- Removing/redesigning `ListNode.bullet_style`.
