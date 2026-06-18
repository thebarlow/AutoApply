# Profile Schema Engine — Design Spec

**Date:** 2026-06-18
**Status:** Approved (brainstorming complete; pending implementation plan)
**Sub-project:** #1 of 5 in the "user-defined resume sections" initiative

## Background

The pipeline is hardcoded around a fixed résumé schema — `Profile → Experience →
Education → Projects → Skills`. This shape is baked into `ParseResponse`,
`ResumeDocument` (`core/schemas.py`), `core/document_assembler.py`
(`CANONICAL_SECTIONS`), `core/document_builder.py` (ref-keyed prose join), the
`resume`/`resume_parse` prompts, the PDF templates in `generator/`, and the React
profile UI. Most résumés do not follow this structure, and users have no way to
add, rename, reorder, remove, or define the structure of their own sections.

The full initiative replaces this rigid typed model with a **user-defined schema
engine** and decomposes into five sequenced sub-projects, each with its own
spec → plan → impl cycle:

1. **Schema engine + data model** ← *this spec*
2. Section builder UI (graphical drag-and-drop creator + preset gallery)
3. Schema-driven LLM generation (generalized prompts, llm_output/llm_input, regen locks)
4. Schema-driven rendering (`generator/` renders arbitrary sections)
5. Onboarding parse that detects/maps novel sections

Sub-project #1 defines the contract the other four consume. It must land
**without breaking the live app**.

## Goal

Introduce a recursive, typed tree as the new source of truth for profile
structure and content, with a backward-compatibility adapter that keeps the
existing generation / rendering / UI working unchanged. Migrate existing
profiles into an equivalent tree that produces byte-identical résumé output.

## Non-goals (owned by later sub-projects)

- The graphical section-builder GUI and preset gallery (#2).
- Schema-driven LLM generation — prompts, `llm_output`/`llm_input` wiring, regen
  locks actually affecting generation (#3).
- Rendering **custom** (non-preset) sections onto generated documents (#4).
  Custom sections are *storable* after #1 but will not appear on generated
  résumés until #4. This is a documented, accepted gap.
- Resume-parse mapping of novel sections (#5).

## Design

### 1. Node model — closed vocabulary, recursive

Every node carries common attributes: `id` (stable UUID), `type`, `name`,
`order` (int, unique among siblings), `visible` (bool). The `type` is drawn from
a closed vocabulary; each type has a fixed attribute contract. A fully arbitrary
tree is explicitly rejected — closed types are what make validation, rendering,
and predictable LLM targeting possible.

| `type`    | Role                         | Type-specific attributes |
|-----------|------------------------------|--------------------------|
| `root`    | the profile / résumé root    | `children: [section]` |
| `section` | a top-level block            | `role` (optional preset id, e.g. `experience`; `null` = custom), `children` (exactly one `list` **or** one `field`/`group`) |
| `list`    | repeating container          | `bullet_style`, `item_template: group`, `children: [group]` (the item instances) |
| `group`   | one item / a bundle of fields| `children: [field]`, `regen_lock` (bool) |
| `field`   | a leaf value                 | `kind ∈ {text, markdown, bullets, taglist}`, `value`, `llm_output` (bool) + `llm_instructions` (str), `llm_input` (bool), `regen_lock` (bool). For `kind=bullets`: `min` (int), `max` (int). |

Field `kind` semantics:
- `text` — single-line string.
- `markdown` — multi-line prose blob.
- `bullets` — a list of markdown bullet strings, bounded by `min`/`max`.
- `taglist` — a flat list of short strings (e.g. skills, technologies).

Generation semantics (defined here, **consumed by #3** — inert in #1):
- `llm_output: true` → the field's value is (re)generated as tailored prose,
  guided by `llm_instructions`.
- `llm_input: true` → the field's value is fed to the generator as context.
  Combined with `visible: false`, this is the "hidden attribute used as LLM
  input" case (e.g. `skills_used`).
- `regen_lock: true` on any `field` or `group` → that node and its descendants
  are frozen and never regenerated.
- `visible: false` → present in the profile and available to generation, but
  never rendered onto a document.

### 1a. The five existing sections expressed in this model

- **Profile**: `section(role=summary) → field(kind=markdown, llm_output=true)`
- **Experience**: `section(role=experience) → list(item_template: group{ title:text, company:text, dates:text, description:bullets[llm_output], skills_used:taglist[visible=false, llm_input=true] })`
- **Education**: `section(role=education) → list(item_template: group{ institution:text, degree:text, field:text, graduated:text, gpa:text })`
- **Projects**: `section(role=projects) → list(item_template: group{ name:text, url:text, description:markdown[llm_output] })`
- **Skills**: `section(role=skills) → list(item_template: group{ category:text, entries:taglist })`
- **Header/contact** (name, email, phone, location, github, linkedin, website):
  `section(role=header) → group{ field(text) per contact attribute }`.

`role` is the stable identifier the adapter (§4) and future renderer (#4) use to
map known sections back to legacy shapes. Custom sections have `role = null`.

### 2. Item template enforcement

A `list` defines **one** `item_template` (a `group` definition). Every child
item conforms to it: adding an item clones the template into a new `group` with
empty values; items cannot have divergent field sets. Editing the template
(add/remove/retype a field) applies to all existing items. This shared-template
rule is what keeps generation and rendering predictable.

### 3. Profile and generated document share one tree model

The **profile is the master tree** (all sections, all items, all fields —
including hidden attributes and full untailored content). A **generated résumé
is a transformed copy of the same node structure**, produced per-job by:
selecting sections/items, filling `llm_output` fields, retaining `llm_input`
fields as context then omitting them from render, and respecting `regen_lock`.
One vocabulary, one validator. (The transform itself is #3/#4; #1 only
establishes that both use the same model.)

### 4. Storage, adapter, and migration (the compatibility seam)

**Storage.** The tree is the source of truth, stored as a `profile_tree` JSON
value inside the existing `user_profile.data` column. No new table. Recursive
Pydantic models live in a new module `core/profile_tree.py`.

**Adapter.** `core/profile_tree.py` exposes `tree_to_legacy(tree) → dict` that
projects the tree down into today's flat profile fields (`first_name`,
`email`, …, `skills`, `work_history`, `education`, `projects`, contact links),
keyed off section `role`. `User._hydrate` derives the legacy typed attributes
from the tree via this adapter, so `core/document_builder.py`,
`core/document_assembler.py`, the generation path, and the React profile UI keep
running **unchanged**.

**Migration.** On load, a profile with no `profile_tree` is converted from its
existing legacy attrs into the default preset tree (§5) and saved
(idempotent — runs once). Sections with no `role` mapping (custom) are preserved
in the tree but ignored by `tree_to_legacy`, so they round-trip in storage but
do not yet reach generated documents.

### 5. Presets

`core/section_presets.py` defines the recommended section subtrees (header,
summary, experience, education, projects, skills) as code, matching §1a. These
seed both migration and the future builder gallery (#2).

## Validation rules

Enforced by the Pydantic models / a `validate(tree)` entry point:
- `type` is in the closed vocabulary; attributes match the type's contract.
- `order` is unique among siblings; `id`s are unique across the tree.
- A `section`'s children is exactly one `list`, one `field`, or one `group`.
- Every `list` child `group` conforms to that list's `item_template`
  (same field `id`s and `kind`s).
- `bullets` fields have `0 ≤ min ≤ max`.

## Testing

- **Golden round-trip:** an existing profile → migrated tree → `tree_to_legacy`
  → legacy attrs → `assemble_resume_markdown` output is **byte-identical** to
  the pre-migration output.
- **Validation unit tests:** closed-vocab rejection, item/`item_template`
  conformance, duplicate `order`/`id`, `bullets` bounds.
- **Migration idempotency:** a second load does not mutate an already-migrated
  tree.

## Files touched

- New: `core/profile_tree.py` (models, validation, `tree_to_legacy`, migration).
- New: `core/section_presets.py` (preset subtrees).
- Modified: `core/user.py` (`_hydrate`/`_to_dict`/`save` to persist + derive from
  `profile_tree`).
- Docs: `core/CONTEXT.md`, `ARCHITECTURE.md` (note the schema engine + the
  documented custom-section rendering gap until #4).

## Open risk / known gap

Custom (non-`role`) sections are storable after #1 but invisible on generated
résumés until #4 ships. Acceptable and documented; surfaced to the user in #2's
builder UI.
