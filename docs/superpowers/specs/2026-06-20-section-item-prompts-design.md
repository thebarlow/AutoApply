# Section/Item Prompts + Profile Editor Modal — Design

**Date:** 2026-06-20
**Status:** Approved (pending spec review)
**Initiative:** Profile schema engine (sub-project #3 continuation — gives Model 2 its real "per-section prompt" thesis)

## Problem

The section-generation comparison harness (Model 1 single-call vs Model 2 per-section)
was built on a premise that was never implemented: Model 2 was supposed to use
**user-authored per-section prompts**, but `SectionNode` has no prompt field. Today
Model 2 only differs by call granularity + per-field `llm_instructions`, so the
comparison tests a weaker hypothesis and is biased toward Model 1.

This design adds the missing piece — authorable **section-level and item-level prompts**
with **context injection via draggable chips** — and reworks the profile editor UX
around it (modal host, pop-out editing, nested lock model).

## Scope

In scope:
- Backend: section/item prompt + lock fields on the profile tree; `{profile.*}` token
  resolver; `section_generator` consuming prompts/locks/tokens.
- Frontend: profile editor moves into a modal; section/item lock toggles; section/item
  prompt editors with a folder-organized chip tray; pop-out editor for prompts and
  long-text values.

Out of scope:
- Productionizing Model 2 (still dev-only compare). Promotion is a later decision.
- Changing the global resume/cover prompts or `PromptModal` behavior (only extracting
  reusable pieces from it).
- Any push to remote / merge to shared main (initiative-wide release constraint stands).

## Data Model (`core/profile_tree.py`)

- **`SectionNode`**: add `locked: bool = False`, `prompt: str = ""`.
- **`GroupNode`** (a list entry — the "item"): add `locked: bool = False`,
  `prompt: str = ""`. The existing `regen_lock` on groups is migrated into `locked`
  (truthy `regen_lock` → `locked = True`) and then removed from groups.
- **`FieldNode`**: unchanged. Keeps `llm_output` (the per-field lock, surfaced as the
  lock icon) and `llm_instructions` (the field-level prompt). `llm_input` remains
  present in the schema but unused by the UI (context injection now happens via prompt
  chips, not a per-field flag).

### Writability rule

A field is **LLM-written** iff **all** hold:
- its `SectionNode.locked == False`, **and**
- its containing list-entry `GroupNode.locked == False`, **and**
- `field.llm_output == True`.

The item-lock and item-prompt apply only to **list entries** (groups inside a `ListNode`).
A non-list section wraps its fields in a structural singleton group; that group gets no
lock/prompt UI and is always treated as unlocked — only the section gate and the field
flags apply there.

Otherwise the field renders **verbatim** and is never sent for generation. Locking is a
gate that nests: a locked section makes its whole subtree verbatim regardless of inner
flags; a locked item makes that entry verbatim; a locked field pins just that field.

### Defaults / backward-compat

- Sections and items default **unlocked** (`locked = False`) — the gate is open.
- Fields keep their existing default: **locked** (`llm_output = False`).
- Net effect for existing profiles: identical to today (nothing is LLM-written until a
  field is explicitly unlocked), but the section/item gates now exist.
- Prompts default to `""` (empty). An empty section/item prompt is valid — an unlocked
  field with an empty section prompt is still written, steered only by its own
  `llm_instructions` (matches "items not locked can be edited by their section-level
  prompts even without an item-level prompt").

### Migration

`db/init_db.py` (or the tree-hydration path) backfills the new fields on load:
sections/items get `locked=False`, `prompt=""`; any group `regen_lock=True` becomes
`locked=True`. Idempotent. No separate Alembic column — the tree is stored as JSON, so
this is a structural backfill of the serialized tree, consistent with prior tree
migrations.

## Token / Chip Scheme

### Tokens

- **Job tokens:** existing `{job.<field>}` (description, company, title, …), resolved by
  the current `_apply_template` against the `job` source.
- **Profile-tree tokens:** `{profile.<section_key>.<field_key>}`.
  - `{profile.<section_key>}` (section-level) injects all of that section's rendered
    field values.
  - `{profile.<section_key>.<field_key>}` injects a single field's value.
  - `<section_key>` is the section's `role` when present, else a slugified `name`;
    `<field_key>` is the field's `key`. Keys are stable identifiers already on the nodes.

### Resolver

A new resolver (alongside `_apply_template`) walks the profile tree to substitute
`{profile.*}` tokens; unknown tokens are left as-is (same tolerance as `_apply_template`).
Applied to section/item prompts at generation time, before the LLM call.

### Chip tray (frontend)

A **collapsing folder tray** rather than a flat wall of chips:
- A top-level `Job` folder containing the job chips.
- One folder per profile section, expandable to its field chips (and a section-level
  chip for the whole section).
- Each chip is draggable; dropping into a prompt textarea inserts its token at the caret
  (reusing `PromptModal`'s caret-insert logic). Folders are collapsed by default so the
  tray stays compact.

## Generation (`core/section_generator.py`)

For each section, in order:
- **Locked section** → emit its current rendered content verbatim; no LLM call.
- **Unlocked section** → build **one** LLM call whose prompt is composed of:
  1. the resolved `section.prompt`,
  2. for each **unlocked** item (list entry): its resolved `item.prompt` prefixed with an
     item reference so the model knows which entry it targets
     (e.g. `For entry "Acme — Senior Engineer (2020–2023)": <item prompt>`); locked items
     are listed as fixed/verbatim context but not rewritten,
  3. per-field `llm_instructions` for each writable field in the section,
  4. resolved `{job.*}` / `{profile.*}` context the user injected.
  The call returns structured content only for writable fields; locked fields/items are
  merged back unchanged.

This is the existing per-section call structure plus the prompt text + lock gating +
token resolution. The dev compare endpoint (`web/routers/dev.py`) is unchanged; Model 2
now reflects authored prompts.

## Frontend

### Editor modal

- Clicking the user's **name** in `UserHome` opens a new **`ProfileEditorModal`** (large,
  centered) that hosts `ProfileTreeEditor`.
- This replaces the cramped inline "push view" currently rendered at the bottom of
  `ProfileDetail`. `ProfileTreeEditor` itself is unchanged in responsibility; only its
  host changes.

### Lock toggles

- Section bars and list-entry bars get the same 🔒/🔓 lock idiom fields already use
  (lock = "the LLM may not write this"). Wired through new `treeOps` (`toggleSectionLock`,
  `toggleItemLock`).

### Prompt editors

- Section bar and each list entry gain a **prompt editor** (collapsible; hidden when the
  node is locked). Fields keep their existing `llm_instructions` box.
- All three prompt editors share a `PromptField` wrapper: textarea + chip tray + pop-out
  button.

### Shared extractions from `PromptModal`

- **`ChipTray`** — the draggable token tray, reworked into the folder-tree form above.
- **caret-insert drop logic** — `onDrop`/`onDragOver` + insert-at-caret, currently inline
  in `PromptModal`.
- **`PromptField`** — textarea bound to a value, with drop handling, chip tray, and a
  pop-out button.

### Pop-out editor

- **`PopOutEditor`** — an expand button on every prompt editor and every multi-line
  field-value input (textarea-kind fields). Opens a centered modal with a large textarea;
  for prompts it also shows the chip tray. Edits commit back to the same value on close /
  apply.

## Build Order (→ plan tasks)

A. **Backend data model** — `SectionNode`/`GroupNode` `locked` + `prompt`; writability
   rule; `regen_lock`→`locked` migration; tree-load backfill. Tests on validation +
   migration.
B. **`{profile.*}` resolver** — tree-walking token substitution; unit tests incl. unknown
   tokens and section-vs-field tokens.
C. **`section_generator`** — consume section/item prompts, lock gating, and resolved
   tokens; one call per unlocked section. Tests with stubbed `call_llm`.
D. **Frontend shared** — extract `ChipTray` (folder tree), caret-insert, `PromptField`,
   `PopOutEditor` from/around `PromptModal`. Component tests.
E. **Editor wiring** — section/item lock toggles + prompt editors in `TreeNode`; `treeOps`
   (`toggleSectionLock`, `toggleItemLock`, `setSectionPrompt`, `setItemPrompt`). Tests.
F. **Modalization** — `ProfileEditorModal` opened from the user name in `UserHome`; remove
   inline push view; long-text pop-out on field values. Tests.

## Testing

- Backend: pytest for tree validation, migration idempotency, resolver substitution,
  `section_generator` composition + lock gating (stub `call_llm` via `core.job`/module
  seam).
- Frontend: Vitest/RTL for lock toggles, prompt editors, chip drag-insert, folder tray
  collapse, pop-out open/apply, modal open from user name.

## Risks / Open Notes

- **Token key stability:** section keys derive from `role`/slug(`name`). Renaming a custom
  section changes its slug and could orphan tokens already typed into other prompts.
  Mitigation: prefer a stable node-id-based key if slugs prove fragile during impl; flagged
  for the plan.
- **Verbatim source for locked nodes:** generation merges locked fields from current tree
  values; ensure the compare harness reads current tree state, not a stale snapshot.
- Still dev-only: no production wiring of Model 2; no remote push (initiative release
  constraint).
