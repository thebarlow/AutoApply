# First-Class List Items, Prompt Modal & Header Editing — Design

**Date:** 2026-06-22
**Status:** Approved (pending spec review)
**Initiative:** Profile schema engine (sub-project #3 continuation — refines the
section/item prompt UX shipped on `feat/section-generation`)

## Problem

The section/item prompt feature shipped, but the editor UX has gaps that surfaced
in manual use:

- The Header section's fields are fixed; users can't add a Kaggle link or drop a
  website they don't have.
- Section reordering shows redundant ↑/↓ arrows and a ▸/▾ expand button — noise in
  a browser-only app where the drag handle reorders and a body-click expands.
- List entries (e.g. jobs under Experience) are second-class: no eye/prompt icons,
  no editable name, not body-click-expandable.
- The pill folder for a list section shows each field N times (3 `summary` pills for
  3 jobs) instead of one entry per job.
- Inline prompt editors clutter every row; the chip tray is always visible.
- Two pill-UX nits: pills land at the caret rather than the drop point, and injected
  pills aren't visually distinct from raw text.
- The eye (visible) toggle does **not** affect the production document — `tree_to_legacy`
  ignores visibility entirely.

## Scope

In scope (editor + generation only; still no remote push — initiative release
constraint stands):

- Tree: a pure prompt-assembly helper; visibility honored in `tree_to_legacy`.
- `section_generator`: send the folded `[Section: … [Item: …]]` prompt format.
- Frontend: prompt-editor modal as the sole prompt surface; first-class list items
  (eye/lock/message icons + double-click rename + body-click expand); per-entry
  sub-folders in the chip tray; add/remove fields on all preset sections; drop-point
  pill insert; green pills; remove ↑/↓ and ▸/▾ buttons.

Out of scope:
- Productionizing Model 2 (still dev-only compare).
- Sub-project #4 schema-driven rendering of *custom* sections/fields — a custom
  header field stores and is editable now but won't appear on the generated PDF until
  #4. (Visibility filtering of *known* fields/entries, below, is in scope because it's
  a one-line guard and makes the existing eye toggle meaningful.)

## Backend

### `core/profile_tree.py`

No schema change — `GroupNode` already has `name`, `locked`, `prompt`, `visible`,
which is everything a first-class list item needs.

**New helper — folded prompt assembly:**

```python
def build_section_prompt(section: SectionNode) -> str:
    """Assemble a section's authoring prompt with its unlocked list entries' item
    prompts nested inside it:

        [<SectionName>: <section.prompt> [<ItemName>: <item.prompt>] ...]

    Empty section/item prompts are omitted; a locked section returns "" (it is never
    authored); locked entries are skipped. Returns "" when nothing is authored.
    """
```

Rules:
- Section locked → `""`.
- Collect `section.prompt` (if non-empty) and, for a `ListNode` child, each unlocked
  entry's `prompt` (if non-empty) as `[<entry name or summary>: <prompt>]`.
- If neither the section prompt nor any item prompt is present → `""`.
- Format: `[<SectionName>: <section.prompt> <item-blocks…>]`. When `section.prompt`
  is empty but item prompts exist: `[<SectionName>: <item-blocks…>]`.

This is the single source of truth for the folded text; the frontend re-implements
the identical format in pure JS for its live preview (no round-trip).

**Visibility in `tree_to_legacy`:**
- Skip a section whose `visible is False`.
- In `_rows()`, skip any list entry whose `visible is False`.
- In the header projection and skills/summary, skip fields whose `visible is False`.
- Idempotent, additive; existing trees (all `visible=True`) are unaffected.

### `core/section_generator.py`

Replace the ad-hoc `guide` / `item_guide` interpolation in `_build_scalar_prompt`
and `_build_list_prompt` with the folded string from `build_section_prompt(section)`,
prepended to the existing JOB / anchors / write blocks. Lock gating, token resolution,
and the `SectionOutput` contract are unchanged. The per-entry `ENTRY id="…"` machinery
that maps output back to fields stays; only the human-readable guidance text changes
to the folded format so the LLM sees `[Experience: … [Research Assistant: …]]`.

## Frontend

### Controls row — sections and list items share one idiom

Both `SectionView` and the list-entry row (`SortableEntry`) render the same control
cluster on the right of their header bar:

- **🔒 lock** (existing) — LLM may not write this subtree.
- **👁 eye** (new on entries; existing on sections/fields) — appears in output.
- **✉ message** (new) — opens the prompt-editor modal for this node. This is the
  **only** way to edit a section/item prompt.

Removed from both: the ↑/↓ `MoveButtons` and the ▸/▾ expand button. Reordering is the
drag handle (⋮⋮) only; expand/collapse is **body-click** on the header bar. List
entries gain body-click expand to match sections (today only sections have it).

`MoveButtons` becomes unused in the tree rows; leave the component in
`structuralControls.jsx` (still exported/tested) but stop rendering it here.

### List items are first-class

- **Editable name:** `RenameLabel` on `group.name`, double-click to rename, same as
  sections. Collapsed bar shows the name, falling back to `entrySummary(item)` when the
  name is empty.
- **Icons:** lock (existing), eye (new — `ops.toggleVisible(item.id)`), message (new).
- **Body-click expand**, drag handle reorder, remove button (existing).
- The inline `PromptField` is removed from the entry; prompt editing moves to the modal.

### `PromptEditorModal` (new component)

Opened by ✉ on a section or item. Hosts the contenteditable pill editor + folder chip
tray (reuses the existing `PromptField`/`PopOutEditor` internals; the chip tray now
lives **only** here, not inline in the tree).

- Title: the node's name (`Section prompt — Experience`, `Item prompt — Research
  Assistant`).
- Editable prompt box bound to `node.prompt` via `ops.setPrompt(id, text)`.
- **Section modal only:** a read-only **folded preview** beneath the editor showing
  `[Experience: … [Research Assistant: …]]`, built live in JS from the section subtree
  (mirrors `build_section_prompt`). Updates as the user types.
- **Locked node:** the modal still opens and the prompt persists, but shows an inline
  note that the prompt is inert while the node is locked (generation skips locked
  nodes).
- Closes on Escape / backdrop / explicit close button (same idiom as
  `ProfileEditorModal`).

The inline section/item `PromptField` blocks in `TreeNode.jsx` are deleted.

### Chip tray — per-entry sub-folders

`buildChipGroups(tree)` changes for **list** sections only:

- A list section becomes a folder containing one **sub-folder per entry** (labelled by
  `entry.name` || `entrySummary`), each expandable to:
  - a **whole-entry pill** → `{profile:<entryId>}` (injects the entry's rendered fields),
  - one **field pill per entry field** → `{profile:<fieldId>}`.
- Non-list sections are unchanged (whole-section pill + field pills).
- This removes the current duplication where template fields appeared once per entry as
  flat repeated pills.

`buildLabelMap` updates correspondingly so entry/field tokens render human-readable
pills (`Experience › Research Assistant`, `Experience › Research Assistant › title`).

### Header / preset field editing

`GroupView`'s `fieldsEditable` becomes **true for all preset sections** (currently only
custom). `SectionChild` passes `fieldsEditable` through for `group` children regardless
of preset. Add/remove field + rename now work in Header, Experience template, etc.

Caveat surfaced in UI copy or docs: a *custom* field added to a preset section stores
and round-trips through the tree but will not render on the generated document until
sub-project #4. Known header/preset keys (kaggle is not one yet) are unaffected by this
caveat only insofar as `tree_to_legacy` recognizes their `key`.

### Pill UX fixes (`PromptField.jsx`)

- **Drop-point insert:** `onDrop` computes the caret from the release coordinates via
  `document.caretRangeFromPoint(e.clientX, e.clientY)` (or `caretPositionFromPoint`
  where that's the available API), inserts the pill there, then emits. Falls back to the
  current selection / append when neither API exists (jsdom).
- **Green pills:** the `.prompt-chip` style becomes
  `bg-emerald-500/15 text-emerald-300 border border-emerald-500/40 rounded px-1`, so
  injected variables read as distinct tokens, not raw text.

## Testing

- **Backend (pytest):**
  - `build_section_prompt`: section-only, item-only, both, locked section → "",
    locked entry skipped, all-empty → "".
  - `section_generator`: the built prompt contains the folded `[Section: … [Item: …]]`
    text (stub `_llm_json_with_retry` via `core.job`).
  - `tree_to_legacy`: invisible section omitted; invisible list entry omitted from
    `work_history`; invisible header field omitted; all-visible tree unchanged
    (regression).
- **Frontend (Vitest/RTL):**
  - Pure helpers: `buildChipGroups` produces per-entry sub-folders with whole-entry +
    field pills (no duplication); folded-preview builder matches expected string.
  - `treeOps`: `toggleVisible` / `rename` / `setPrompt` on a list-entry id.
  - Controls: ✉ opens `PromptEditorModal`; no ↑/↓ or ▸/▾ buttons rendered; entry
    eye/message icons present; double-click renames an entry; body-click expands an
    entry.
  - `PromptEditorModal`: section variant shows folded preview; locked node shows the
    inert note; chip insert works; only place chips appear.
  - Preset section shows add-field form.
- **Manual (deferred to user):** drop-point insert and green pills (jsdom can't exercise
  `caretRangeFromPoint` or CSS); full save round-trip incl. entry rename + visibility on
  a generated document.

## Build Order (→ plan tasks)

A. **Backend tree:** `build_section_prompt` + visibility in `tree_to_legacy`; tests.
B. **`section_generator`:** consume folded prompt; tests.
C. **Chip tray sub-folders:** `buildChipGroups`/`buildLabelMap` per-entry; folded-preview
   JS helper; tests.
D. **`PromptEditorModal`:** new component + remove inline `PromptField`; tests.
E. **First-class items + controls cleanup:** entry eye/message/rename/body-expand;
   remove ↑/↓ and ▸/▾; wire `toggleVisible`/`rename`/`setPrompt` for entries; tests.
F. **Preset field editing:** `fieldsEditable` for presets; tests.
G. **Pill UX:** drop-point insert + green style; manual verify.

## Risks / Open Notes

- **`caretRangeFromPoint` browser support / jsdom gap:** handled by feature-detect +
  fallback; covered manually, not in unit tests.
- **Folded-format drift:** the JS preview and Python `build_section_prompt` must agree;
  a single documented format string in both, with a frontend unit test pinning the
  expected output, mitigates drift.
- **Visibility scope creep:** filtering is limited to the existing legacy keys; it does
  not attempt to render unknown/custom sections (that is #4).
- Still dev-only Model 2; no remote push.
