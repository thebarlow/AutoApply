# 4B — Wire tree-v1 into production (Profile Schema Engine #4B)

**Date:** 2026-06-22
**Status:** Design approved, spec under review
**Parent:** Profile Schema Engine #4 (full tree swap) — see
`2026-06-22-schema-driven-document-rendering-design.md`
**Release constraint:** merges to LOCAL `main` only — do NOT push `main` until the whole
swap (#4–#6 and #5) is complete.

## Problem

4A shipped two pure modules — `core/document_tree.py`
(`build_resume_document_tree(root, authored)`) and `core/tree_assembler.py`
(`assemble_resume_tree_markdown(root)`) — with golden tests, but nothing in the running
app calls them except the admin compare harness. Production résumé generation still runs the
fixed-model path: `generate_resume_md` → `ResumeGeneration` → `build_resume_document` →
`ResumeDocument` → `documents.structured_json` → `assemble_resume_markdown` → frontmatter +
body `.md` → pandoc/Jinja/CSS PDF (with `render_pdf` stripping Education from the body and
re-injecting it from frontmatter). Custom/user-defined sections never reach a generated
résumé.

4B makes the **production** résumé pipeline produce, store, render, and refine a tree-v1
document, so any user-defined section appears on the generated PDF, while existing legacy
`documents` rows keep rendering unchanged.

## Phasing: 4B-1 then 4B-2

The per-section critique-and-selective-regenerate refinement engine is a **new** engine
(today's loop does one whole-document eval call → single score → full prose-patch). To keep
each merge independently testable, 4B splits:

- **4B-1 — Tree-v1 in production (this plan's target).** Generation → tree-v1 storage →
  generic render → **full PDF/frontmatter retire** → all read paths branch on the `schema`
  discriminator. Refinement of tree-v1 docs uses an **interim** strategy that reuses the
  existing whole-document eval loop: on a refine turn, re-run the per-section generator
  (4A path) for **all** `llm_output` sections with the critique injected, rebuild the
  document tree, re-persist, re-render. Legacy rows keep using the `ResumeGeneration`
  prose-patch.
- **4B-2 — Per-section refinement engine.** Replace the interim strategy: one eval LLM call
  returns a per-section breakdown (`{section: {score, issues}}`); only sub-threshold
  sections are regenerated. Its own spec → plan → impl cycle.

This document specifies **4B-1**. 4B-2 is recorded in the roadmap and gets its own spec.

## The `schema` discriminator (no data migration)

`documents.structured_json` for `doc_type="resume"` gains a top-level `schema` key:

- New résumés write `schema: "tree-v1"` — the serialized document tree (a `RootNode` JSON).
- Existing rows have no `schema` key → treated as legacy `ResumeDocument`.
- Unknown `schema` value → treated as legacy `ResumeDocument` (safest default).

A single helper resolves the discriminator from a raw JSON string so every read path branches
identically. No existing rows are migrated; old jobs render through the legacy assembler
forever.

Cover letters are untouched — `CoverDocument` has no `schema` key and stays on the typed path.

## Generation (`generate_resume_md`)

`generate_resume_md` switches to the tree path:

1. `root = user.profile_tree_root()`
2. resolve the resume prompt and `{job.*}`/`{profile.*}` tokens (the dev-harness `resolve`
   closure becomes the production path),
3. `authored = generate_resume_by_section(root, prompt, client, model, resolve=resolve)`,
4. `doc_tree = build_resume_document_tree(root, authored)`,
5. persist `doc_tree` JSON under `schema:"tree-v1"`,
6. `write_resume_markdown` renders it via `assemble_resume_tree_markdown`.

The single-call `ResumeGeneration` / `build_resume_document` path is retained **only** for
legacy refine of pre-existing rows; it is no longer the generation path. The fixed
`ResumeGeneration` schema and `build_resume_document` are **not deleted** in 4B-1 (legacy
refine still needs them).

## Storage serialization

The document tree is a `RootNode`. 4B-1 adds serialize/deserialize for the node tree
(`to_json`/`from_json` or Pydantic-model dump) that round-trips losslessly, with the
`schema:"tree-v1"` marker injected at the top level on write and read for branching. Tests
pin round-trip equality.

## Render paths — branch on discriminator

Each load site resolves the discriminator and dispatches:

| Site | Legacy (`ResumeDocument`) | tree-v1 |
|---|---|---|
| `write_resume_markdown` | frontmatter + `assemble_resume_markdown` | `assemble_resume_tree_markdown` (no frontmatter) |
| `_render_meta` | header/education from `ResumeDocument` | empty/none — contact+education are in the body, not meta |
| `run_ats_check` (load doc) | `ResumeDocument` | document tree (ATS gate consumes it; gate rework is 4C — 4B-1 adapts the loader, keeps the existing checks running) |
| `intake_pipeline._restore_best` | `ResumeDocument` re-persist + `write_resume_markdown` | tree-v1 re-persist + `write_resume_markdown` |
| `routers/jobs.get_document` GET | `_json.loads(structured_json)` | `_json.loads(structured_json)` (returns tree-v1 JSON as-is) |
| `routers/jobs` turn-snapshot render | `assemble_resume_markdown` | `assemble_resume_tree_markdown` |
| `_ensure_document_row` / parse-on-read | reconstruct `ResumeDocument` | unchanged — only fires when NO row exists (legacy on-disk `.md`); new tree-v1 docs always have a row |

`write_resume_markdown`'s signature widens to accept either a `ResumeDocument` or a document
tree (or split into two helpers dispatched by the caller).

## PDF / frontmatter retire (full, in 4B-1)

For tree-v1 résumés:

- `write_resume_markdown` emits **no YAML frontmatter** — contact and education are ordinary
  body sections rendered by `assemble_resume_tree_markdown`'s contact/education templates.
- `render_pdf` no longer strips Education from the body or re-injects contact/education from
  `meta` **for tree-v1** (`_render_meta` returns empty meta, so the existing injection is a
  no-op, but the Education-stripping special-case must be guarded so it only applies to the
  legacy frontmatter path).
- `resume_template.html` (Jinja2) is reworked so the rendered contact block (name as H1,
  ATS-ordered contact line/grid) and education rows come from the **body HTML** produced by
  pandoc from the tree markdown, styled by CSS — not from `meta`. ATS-load-bearing contact
  ordering is preserved by the contact section renderer + template CSS, not frontmatter.
- `max_pages=1` auto-shrink is unchanged.
- Legacy rows keep rendering through the existing frontmatter+template path unchanged.

This is the sizable piece of 4B-1: the template must render a résumé whose contact/education
now arrive as body markdown while still looking like today's output and passing ATS contact
parsing.

## Interim refinement (4B-1)

`_refine_doc_md` for `doc_type="resume"` branches on the discriminator:

- **Legacy row:** unchanged — `ResumeGeneration` prose-patch via `apply_resume_patch`.
- **tree-v1 row:** re-run `generate_resume_by_section` for all `llm_output` sections with the
  critique (`issues`) injected into the section prompts, rebuild the document tree from the
  fresh authored values, re-persist under `schema:"tree-v1"`, `write_resume_markdown`.

The auto-refine loop (`_run_doc_refinement` in `intake_pipeline.py`) and
`run_user_feedback_refine` call through `refine_resume_md` → `_refine_doc_md`, so they work
unchanged once `_refine_doc_md` branches. Per-turn snapshots (`_save_turn_snapshot`) store
whatever JSON is in the row (tree-v1 or legacy) — `_restore_best` re-renders by discriminator.

**Critique injection:** the section prompts gain an optional critique slot; when present
(refine turn) the issues are passed in, when absent (initial generation) they're omitted.
4B-1 wires the plumbing; the per-section *scoring* that decides WHICH sections to regen is
4B-2 — in 4B-1 every `llm_output` section regenerates each refine turn.

## Interim editor gap (accepted)

The legacy `DocumentModal` (`react-dashboard/.../document/`) renders `ResumeDocument` shape;
it cannot render or edit a tree-v1 document (rebuilt generically in 4D). Between 4B and 4D,
opening the modal on a tree-v1 résumé degrades. Because nothing is pushed until the whole
swap ships, this only affects the local dev instance and is an accepted interim limitation.
4B-1 makes the GET endpoint return tree-v1 JSON honestly (it does not fake a `ResumeDocument`
shape); the frontend graceful-degradation/rebuild is 4D. Direct-edit PUT of tree-v1 is
likewise 4D.

## Error handling

- Per-section generation failure falls back gracefully (as 4A/#3 already do) — a failed
  section keeps empty/stored values, never crashes the document.
- A `tree-v1` row that fails to deserialize raises a clear error at the load site (caller
  surfaces it as the existing `last_result_error`/HTTP path), rather than silently rendering
  blank. (Parse-on-read reconstruction for tree-v1 is not built in 4B-1 — new tree-v1 rows
  are always written by us; the legacy `.md` reconstruct path stays for legacy only.)
- Unknown `schema` → legacy `ResumeDocument` path.

## Testing

- **Discriminator helper:** legacy JSON (no `schema`) → legacy; `schema:"tree-v1"` → tree;
  unknown → legacy.
- **Serialization:** document tree round-trips through serialize/deserialize losslessly,
  including locked nodes, list entries, groups, and a custom section.
- **Generation:** `generate_resume_md` writes a row with `schema:"tree-v1"` and a `.md` with
  no frontmatter; a custom section's heading appears in the `.md`.
- **Render branch:** a tree-v1 row renders via `assemble_resume_tree_markdown`; a legacy row
  renders identically to before via `assemble_resume_markdown` (golden).
- **PDF:** contact + education appear in tree order via the template (no frontmatter);
  Education is not double-rendered; one-page shrink still works; legacy PDF path unchanged.
  (PDF rendering needs Chromium/pandoc — gate behind the existing render-test marker; assert
  on emitted HTML/markdown where a full render isn't available in CI.)
- **Interim refine:** a tree-v1 row through `_refine_doc_md` re-runs section generation,
  re-persists `schema:"tree-v1"`, and re-renders; a legacy row still uses the prose-patch.
- **restore_best:** a tree-v1 best turn restores and re-renders without raising.

## Out of scope (4B-1)

- Per-section eval scoring / selective regeneration — **4B-2**.
- ATS gate rework (drop fixed-heading checks) — **4C**.
- DocumentModal generic rebuild + tree-v1 editing/PUT — **4D**.
- Deleting `ResumeGeneration` / `build_resume_document` / `core/tree_render.py` — legacy
  refine still uses the first two; `tree_render.py` removal is a tracked 4B carry-forward
  needing approval, done once nothing references it.
- Cover-letter tree-ification.
- User-customizable templates + live preview — **#6**.
