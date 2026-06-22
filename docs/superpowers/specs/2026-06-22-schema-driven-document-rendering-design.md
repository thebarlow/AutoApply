# Schema-driven document rendering (Profile Schema Engine #4)

**Date:** 2026-06-22
**Status:** Design approved, spec under review
**Sub-project:** Profile Schema Engine #4 of 5 (full tree swap)
**Release constraint:** merges to LOCAL `main` only — do NOT push `main` until the whole swap (#1–#5) is complete.

## Problem

After #1–#3, the profile is a recursive tree (`core/profile_tree.py`) and per-section
LLM generation runs against it (`core/section_generator.py`). But the **generated
document** is still built on the fixed 5-section typed model: `ResumeGeneration`
→ `build_resume_document` → `ResumeDocument` (Profile/Experience/Education/Projects/
Skills) → `documents.structured_json` (source of truth) → `assemble_resume_markdown`
→ `.md` → pandoc/Jinja/CSS → PDF. Custom/added sections and fields are storable and
editable in the profile tree but **do not appear on generated résumés** — `tree_to_legacy`
only projects the known legacy keys, and the assembler/templates render fixed sections.

#4 makes the document pipeline render the tree's sections/fields generically, so any
user-defined section reaches the rendered résumé.

## Scope decision: full tree swap (résumé only)

The typed résumé document pipeline is **retired** in favor of a tree-based document.
The cover letter stays typed (`CoverDocument` = body + signoff; not sectioned, the tree
buys nothing). Cover build/assemble/parse paths are untouched by #4.

## Core model: the "document tree" as the new source of truth

At generation time, `section_generator.generate_resume_by_section` produces authored
values keyed by field-node id (`field_id -> str | list[str]`). A new builder materializes
a **document tree**: a deep copy of the profile tree, with

- nodes that are not visible **pruned**,
- `context_only` (`llm_input and not llm_output`) fields **dropped**,
- authored values **baked into** outputable fields' `value`,
- locked sections/entries **carried through verbatim** (their stored values),

producing a self-contained snapshot with **no live-profile dependency** — the same
generation-time snapshot guarantee `_render_meta` provides today. This serialized
document tree replaces `ResumeDocument` in `documents.structured_json` **for résumés**.

### Back-compat (no data migration)

`documents.structured_json` for `doc_type="resume"` gains a `schema` discriminator:

- New résumés store `schema: "tree-v1"` (the document tree).
- Existing rows have no discriminator → treated as legacy `ResumeDocument`.

All read paths (render, DocumentModal GET, `_render_meta`, parser/backfill) branch on
the discriminator. Legacy rows keep rendering through the existing `assemble_resume_markdown`.
**No migration of existing `documents` rows.** Old jobs never break.

## Generic renderer

Promote `core/tree_render.py` (currently throwaway, used only by the dev compare harness)
to a production canonical renderer, or add `assemble_resume_markdown_from_tree(doc_tree)`
alongside the existing assembler in `core/document_assembler.py`:

- section name → `## ` heading,
- list entries → per-entry blocks (with optional `### ` entry heading from a designated
  title field), groups → field lines, fields → `**Name:** value` or bullets,
- `markdown`-kind fields → passthrough.

**Every section renders generically in tree order — including contact/header and
education.** There is no canonical reordering (the user's section order is authoritative).

### Frontmatter retired (no data channel)

Today contact + education travel to the template via a YAML front-matter block, whose sole
purpose was to *protect* those values from the LLM. Under the tree model that protection is
structural and free: contact and education fields are not `llm_output` fields, so
`section_generator` never authors them — they pass through verbatim regardless. **The YAML
front-matter data channel is therefore removed.** Contact and education are ordinary sections
in the document tree, rendered by the same generic path as every other section.

### Presentation is template-driven, not frontmatter-driven

The one thing the old frontmatter+template did worth keeping is the *visual treatment* (name
as H1, the ATS-ordered icon contact grid, styled education rows). That is a **formatting**
concern, not a data-transport one. The renderer walks the document tree and renders each
section through a **template/formatter** selected by the section's `role`/`kind` (contact →
icon-grid template, education → edu-row template, custom/unknown → generic template). Data is
tree-driven; presentation is template-driven. #4 ships **default** templates only;
user-customizable templates + live preview are **sub-project #6** (below).

## PDF / template rework

`render_pdf` (`core/utils.py`) currently strips Education from the Markdown body and
re-injects it from frontmatter after Profile. Under the tree swap this special-casing and the
frontmatter education/contact injection are **removed**: contact and education are normal
sections rendered (via their default templates) in tree order. ATS-load-bearing contact
ordering is preserved by the contact template, not by frontmatter.

`max_pages=1` auto-shrink behavior is unchanged.

## ATS gate rework

Real ATS parsers classify sections via proprietary, vendor-specific synonym dictionaries we
cannot reproduce, and there is no universally-required section (freshers/students/career-changers
legitimately lack work history). So #4 **drops the fixed-heading hard-block entirely**:

- **Remove** the "required sections present" check and any literal heading matching from
  `check_mechanical`.
- **Keep** (all field-agnostic): contact present & parseable at top, machine-readable
  text-layer, glyph-junk detection, and the per-job **`ext_required_skills` survive in the
  extracted PDF text** check (the real per-job signal — section-name independent).
- **Keep** the semantic LLM roundtrip (`check_roundtrip`) unchanged — vendor-agnostic proxy
  for "can a parser read this".

No roles, no synonym map.

## DocumentModal rebuild (generic tree editor)

The interactive post-generation editor (`react-dashboard/src/components/widgets/document/`:
`InteractiveResume`, `ResumeSection`, `items`, `ItemEditor`, `ItemPopover`) is hardwired to
`ResumeDocument`. Rebuild it to render/edit the **document tree** generically (per-section and
per-item edit + feedback), reusing the profile-tree React patterns (`profile-tree/TreeNode.jsx`
et al.). The feedback refine path (`POST /{doc_type}/feedback` → `run_user_feedback_refine`)
retargets tree nodes instead of typed refs. Cover-letter editing is unchanged.

## Internal phasing (each its own plan → subagent impl, merged to local `main`)

Switching production generation to the tree path cascades into the auto-refine loop and
feedback-refine (both `ResumeDocument`-based, both auto-fire post-generation). To isolate that
risk from the pure rendering engine, #4 is **four** phases:

- **4A — Pure foundation (no production wiring).** `core/document_tree.py`
  (`build_resume_document_tree(root, authored)` — prune invisible + `context_only` nodes, bake
  authored values, keep locked verbatim) + a generic **template-composed** section renderer
  (promote `core/tree_render.py`) with **default templates for contact + education** (no
  frontmatter). All pure functions with golden tests. The running app is unchanged.
- **4B — Wire tree-v1 into production (headline win).** `generate_resume_md` →
  `section_generator` → document tree → store under `schema:"tree-v1"`;
  `_render_meta`/`write_resume_markdown` branch on the discriminator; PDF/template rework
  (frontmatter retired); make the auto-refine loop + feedback-refine tree-aware. Custom sections
  now appear on generated PDFs; contact/education flow generically. Legacy rows still render via
  the old assembler.
- **4C — ATS gate rework.** Drop fixed-heading checks; keep field-agnostic mechanical +
  semantic layers.
- **4D — DocumentModal generic rebuild + feedback-on-tree.** Largest, mostly frontend.

### Relationship to sub-project #6 (user-formatted PDF + live preview)

#4 ships **default** section templates only. **Sub-project #6** (sequenced #4 → **#6** → #5)
adds a live in-dashboard PDF render and a constrained, user-customizable template system
(the user controls how each section/item renders), with ATS-safety enforced by the templates
themselves. #4's template-composed renderer is the foundation #6 builds on; the 4D DocumentModal
is #6's UI home. #6 gets its own spec.

## Error handling

- Generation snapshot failure for a section falls back gracefully (as #3's per-section
  generation already does) — a failed section is kept with empty/stored values, never crashes
  the whole document.
- A `tree-v1` row that fails to deserialize falls back to a parse-on-read reconstruction path
  (mirrors today's `document_parser` backfill behavior) rather than 404/500.
- Unknown `schema` value → treated as legacy `ResumeDocument` (safest default).

## Testing

- **Builder (4A):** document-tree materialization prunes invisible/context-only nodes, bakes
  authored values, preserves locked entries, drops live-profile dependency (mutating the profile
  after snapshot doesn't change the document).
- **Renderer (4A):** golden-markdown tests for a preset-only tree (contact + education render
  generically, no frontmatter) and for a tree with a custom section (custom section appears).
- **Back-compat (4B):** a legacy `ResumeDocument` row still renders identically; a `tree-v1` row
  renders via the generic path.
- **PDF (4B):** contact + education appear in tree order via their templates (no frontmatter);
  ATS contact ordering preserved; one-page shrink still works.
- **ATS (4C):** a custom-only résumé (no section literally named "Experience") passes the gate;
  contact/text-layer/glyph/required-skills checks still fire.
- **DocumentModal (4D):** Vitest + RTL — renders an arbitrary document tree, edits a custom field,
  submits feedback against a custom node.

## Out of scope

- Cover-letter tree-ification.
- Section roles / ATS synonym maps.
- User-customizable templates + live PDF preview — **sub-project #6** (sequenced after #4).
- #5 onboarding parse (maps novel uploaded résumé sections onto the schema).
- Migrating existing `documents` rows (handled by the read-time discriminator instead).
