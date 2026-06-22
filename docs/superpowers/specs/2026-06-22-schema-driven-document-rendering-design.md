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
- `markdown`-kind fields → passthrough,
- the **contact/header** preset section is NOT rendered into the body — it is projected
  into YAML frontmatter (name/email/phone/location/social) to feed the template's icon grid.

Every non-header section renders generically into the body in **tree order** (no canonical
reordering — the user's section order is authoritative).

## PDF / template rework

`render_pdf` (`core/utils.py`) currently strips Education from the Markdown body and
re-injects it from frontmatter after Profile. Under the tree swap this special-casing is
removed: **Education is a normal body section ordered by the tree.** The header/contact is
still rendered by `resume_template.html` from frontmatter (the 2×3 icon grid). The template's
hardcoded Education injection block is removed; the body fragment carries all sections in order.

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

- **4A — Document tree + generic renderer + PDF rework.** Generation stores a `tree-v1`
  document tree; render MD/PDF generically; legacy rows still render via the old assembler.
  **Ships the headline win: custom sections appear on generated PDFs.**
- **4B — ATS gate rework.** Drop fixed-heading checks; keep field-agnostic mechanical +
  semantic layers.
- **4C — DocumentModal generic rebuild + feedback-on-tree.** Largest, mostly frontend.

## Error handling

- Generation snapshot failure for a section falls back gracefully (as #3's per-section
  generation already does) — a failed section is kept with empty/stored values, never crashes
  the whole document.
- A `tree-v1` row that fails to deserialize falls back to a parse-on-read reconstruction path
  (mirrors today's `document_parser` backfill behavior) rather than 404/500.
- Unknown `schema` value → treated as legacy `ResumeDocument` (safest default).

## Testing

- **Builder:** document-tree materialization prunes invisible/context-only nodes, bakes
  authored values, preserves locked entries, drops live-profile dependency (mutating the profile
  after snapshot doesn't change the document).
- **Renderer:** golden-markdown tests for a preset-only tree (output matches the legacy assembler
  closely enough for known sections) and for a tree with a custom section (custom section appears).
- **Back-compat:** a legacy `ResumeDocument` row still renders identically; a `tree-v1` row renders
  via the generic path.
- **PDF:** Education appears in tree order; contact grid still populated from frontmatter; one-page
  shrink still works.
- **ATS (4B):** a custom-only résumé (no section literally named "Experience") passes the gate;
  contact/text-layer/glyph/required-skills checks still fire.
- **DocumentModal (4C):** Vitest + RTL — renders an arbitrary document tree, edits a custom field,
  submits feedback against a custom node.

## Out of scope

- Cover-letter tree-ification.
- Section roles / ATS synonym maps.
- #5 onboarding parse (maps novel uploaded résumé sections onto the schema) — follows #4.
- Migrating existing `documents` rows (handled by the read-time discriminator instead).
