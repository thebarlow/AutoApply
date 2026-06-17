# Per-Section Resume Content & Format Control — Design

**Date:** 2026-06-17
**Status:** Approved (umbrella spec). Sub-project A detailed for implementation; B and C scoped only.

## Problem

Today the résumé is generated as a whole: one LLM call against a single `resume`
prompt produces all tailored prose, the profile contributes fixed structural facts,
and a whole-résumé eval/refine loop + ATS gate finish it. Users cannot:

- Control how each résumé section is composed or formatted from the profile view.
- Keep some sections verbatim (e.g. education) while rewriting others.
- Rewrite only *some* items in a section (e.g. only certain project descriptions),
  or protect parts (titles/dates are already structural, but the control isn't explicit).
- Pair a dedicated prompt with a section for higher-quality, per-section rewrites.
- Create new sections (Certifications, Publications, …) or rename existing ones.

## Goals

- Per-section control over **content structure/order**, **visual layout/style**, and
  **rewrite behavior**, driven from the profile view.
- Per-item rewrite toggles with a section-level default that items override.
- Section-paired prompts: each rewrite-enabled section uses its own customizable prompt
  and its own LLM call + eval/refine loop; a final ATS gate runs on the assembly.
- User-creatable, renamable, reorderable, deletable sections; custom sections hold either
  a structured entry list or a free-form text block.

## Non-Goals (this umbrella)

- Cover-letter restructuring (unchanged for now).
- Changing the source of truth for built-in structured data (profile `work_history`,
  `education`, `projects`, `skills` remain authoritative).

## Decomposition

Three sub-projects share one per-section config object stored on the profile
(`User.data.resume_sections`). Each owns a slice; each gets its own spec → plan → impl
cycle. **Ship order: A first.**

- **Sub-project A — Rewrite behavior** (detailed below; ship first). Consumes `rewrite`,
  per-item `items[].rewrite`, and `prompt_ref`. Introduces per-section LLM calls,
  per-section eval/refine, final ATS gate, and the section-list data model.
- **Sub-project B — Content structure/order.** Consumes section list order, item ordering,
  and field-visibility flags (extends `format`). Mostly no-LLM reshaping of the assembled
  document.
- **Sub-project C — Visual layout/style.** Consumes `format` (bullets vs paragraphs,
  density, field visibility) → generator Jinja2 templates / CSS.

## Shared Data Model

`resume_sections` is an **ordered list** of section objects in `User.data`:

```jsonc
resume_sections: [
  { "id": "profile", "label": "Profile", "kind": "profile", "builtin": true,
    "rewrite": true, "prompt_ref": "<key|null>", "format": { /* B/C */ } },

  { "id": "exp", "label": "Experience", "kind": "experience", "builtin": true,
    "rewrite": true, "prompt_ref": "<key|null>", "format": {},
    "items": { "<ref>": { "rewrite": false } } },          // per-item override

  { "id": "edu", "label": "Education", "kind": "education", "builtin": true,
    "rewrite": false, "format": {} },                       // verbatim by default

  { "id": "u_abc123", "label": "Certifications", "kind": "entries", "builtin": false,
    "rewrite": true, "prompt_ref": "<key|null>", "format": {},
    "content": [ { "id": "...", "title": "", "subtitle": "", "start": "", "end": "",
                   "description": "", "rewrite": true } ] },

  { "id": "u_def456", "label": "Summary Note", "kind": "text", "builtin": false,
    "rewrite": true, "prompt_ref": "<key|null>", "content": { "text": "" } }
]
```

Field semantics:

- **`id`** — stable identifier (slug for built-ins, `u_<rand>` for custom). Never changes.
- **`label`** — user-editable display name (rename edits this only).
- **`kind`** — drives content source + rendering:
  - Built-in: `profile`, `experience`, `education`, `projects`, `skills` → items pulled
    from the existing profile structured data (unchanged).
  - Custom: `entries` (structured item list) or `text` (prose block), stored inline in
    `content`.
- **`builtin`** — built-in sections can be hidden/reordered but their underlying profile
  data is retained even if the section is removed.
- **`rewrite`** — section-level default for LLM rewrite.
- **`items[<ref>].rewrite`** — per-item override of the section default (for structured /
  `entries` kinds). Excluded items keep verbatim prose.
- **`prompt_ref`** — optional per-section prompt override key; falls back to the seeded
  generic `resume_section` default prompt.
- **`format`** — reserved for Sub-projects B (order/field visibility) and C (visual style).

**Migration / defaults:** when `resume_sections` is absent, synthesize the current
behavior — a default ordered list (profile, experience, skills, projects, education) with
`rewrite` matching today's behavior (prose sections on, education/skills verbatim). No data
is lost; the field is additive on `User.data`.

## Per-Section Prompts

- Seed a generic `resume_section` prompt (default), parameterized by section label/kind +
  the section's items + the job posting.
- A section may override it via `prompt_ref`, stored in the DB `prompts` table under a
  section-scoped key (e.g. `resume_section:<section_id>`), reusing the existing DB-backed
  prompt system and the `PromptsSection` editor UI.
- This works uniformly for custom sections, which cannot have a fixed prompt type.
- The legacy monolithic `resume` prompt is retired from the primary path (kept only for
  backfill/fallback if needed).

## Sub-Project A — Rewrite Pipeline (ship first)

Generation (résumé path in `core/job.py`), iterating the section list in order:

1. Resolve the section's effective config (section `rewrite` default + per-item overrides).
2. **Verbatim** (section rewrite off, or item override off): take prose directly from the
   profile/inline content — **no LLM call**.
3. **Rewrite on**: build a section-scoped context (that section's rewrite-enabled items +
   the job posting) and call the LLM with the section's resolved prompt. Excluded items
   keep verbatim prose. Output validates against a new per-section schema
   (`ResumeSectionGeneration`, reusing `ResumeExperience` / `ResumeProject` / entry shapes).
4. **Per-section eval/refine loop** — reuse the existing turns / pass-score machinery,
   scoped to the section; keep best.
5. **Assemble** all section outputs into a `ResumeDocument` via `document_builder`,
   extended to walk the section list instead of fixed fields.
6. **Final ATS gate** runs once on the assembled résumé; on failure, surface it and allow
   targeted re-refine of the relevant section(s).

**Metering:** each section LLM call and its refine turns are wrapped in
`meter_action(action="generate_resume:<section_id>")`. Total cost = Σ (enabled sections ×
refine turns) — materially higher than today. The UI shows a cost estimate before
generating.

**Schemas / builder / parser:**
- `core/schemas.py`: add `ResumeSectionGeneration`; make `ResumeDocument` section-aware
  (ordered sections, each carrying `kind` + items/text).
- `core/document_builder.py` / `core/document_assembler.py`: iterate the section list.
- `core/document_parser.py`: round-trip the section-aware document (backfill support).

**UI (`react-dashboard/.../ProfileDetail.jsx`):** clicking a section opens a config panel:
rewrite toggle, per-item rewrite toggles, prompt picker/editor (reuse `PromptsSection`),
and add / rename / delete / choose-custom-kind controls. Format/order controls are stubbed
for Sub-projects B and C.

## Testing

- **Unit:** section-config resolution (defaults + per-item cascade); verbatim passthrough
  makes no LLM call; per-section generate with rewrite on/off; custom `entries` and `text`
  sections; assembly ordering; ATS gate on the assembled doc; per-section metering action
  keys.
- **Integration:** full multi-section generate mixing rewrite and verbatim sections,
  asserting only enabled sections incur LLM calls/debits and the assembled document
  preserves order and verbatim content.

## Risks / Notes

- Largest change is the generation core, but it's isolated to the résumé path; the cover
  letter is untouched.
- Cost can climb quickly with many rewrite-enabled sections × refine turns — the cost
  estimate and per-item toggles are the main mitigations.
- The section-aware `ResumeDocument` is a breaking shape change; existing documents must be
  regenerated (or parsed/backfilled via `document_parser`).
