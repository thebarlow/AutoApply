# Document editor layout rebuild + configurable page limit

**Date:** 2026-06-24
**Status:** Design approved
**Branch:** `feat/schema-rendering-4d` (follow-on to the 4D DocumentModal tree rebuild)
**Release constraint:** merges to LOCAL `main` only — do NOT push `main` until the whole Profile Schema Engine swap (#4–#6 + #5) is complete.

## Problem

Two gaps surfaced during manual QA of the 4D tree-v1 document modal:

1. **Editor layout is flat.** `react-dashboard/src/components/widgets/document/DocumentTree.jsx`
   flattens every field via `fieldsOf`, so each field stacks one-per-row and multi-entry
   sections (e.g. Experience with several jobs) blur together — there is no visual grouping and
   single-line text inputs do not share rows. The profile editor (`profile-tree/TreeNode.jsx`)
   already solves this with a 2-col grid and collapsible cards; the document editor should adopt
   the same idioms (values-only).
2. **Page limit is hardcoded.** `max_pages=1` is hardcoded at six résumé-render call sites. Users
   need to control résumé length (1 page, N pages, or unlimited) from their profile.

## Part A — `DocumentTree.jsx` structural rebuild

Rebuild the renderer to preserve the document tree's structure instead of flattening it, porting
the profile editor's layout idioms while staying **values-only** (no drag, no add/remove/rename,
no lock/visibility toggles — those remain in the profile editor).

### Section rendering

- Each **section** renders as a collapsible bordered card (`border border-space-border
  rounded-xl p-4`), **collapsed by default**. Clicking the header toggles expand/collapse.
- The section header carries the section name and, for **unlocked** sections, a feedback 💬
  control (toggles a per-section note textarea). Locked sections show no feedback control.

### Section-child dispatch

Mirror the profile-tree `SectionChild` dispatch on the section's single child node:

- **bare field** (summary hero, skills taglist) → render the field directly at full width.
- **group** (fixed-shape field set) → a **2-col grid** (`grid grid-cols-2 gap-x-4 gap-y-3`):
  `text`-kind fields occupy one column (so two share a row, e.g. Company | Title, Start | End);
  multi-line kinds (`markdown`, `bullets`, `taglist`) span both columns (`col-span-2`). This is
  `GroupView`'s grid, minus the field add/remove affordances.
- **list** (repeating entries) → each **entry** renders as its own collapsible sub-card
  (bordered, collapsed by default) with a summary label derived from the entry's first non-empty
  field value (the `entrySummary` idiom). The entry's fields render via the same group grid.

### Locked fields

Fields whose owning section/entry is locked render read-only (the `readOnly` / `valueOnly`
props already threaded through `FieldWidget`); no editor, no feedback control.

### Feedback granularity (changed from 4D Task 4)

Per-field feedback 💬 is **removed**. Feedback is collected at **two levels**:

- **section level** — one 💬 per unlocked section card (covers bare-field sections like Summary
  and Skills).
- **entry level** — one 💬 per unlocked list entry sub-card.

Rationale: regeneration is per-section regardless of anchor granularity, entry-level already gives
fine attribution, and per-field buttons clutter the 2-col grid. Each note still carries
`{section, label, note}`; the owning section name drives selective regen exactly as in 4D. The
note `section` is the owning section's name; `label` is the section name (section-level) or the
entry summary/name (entry-level). The DocumentModal feedback footer contract
(`collected` → `submitFeedback` → `build_feedback_issues`) is unchanged.

### Tests

`DocumentTree.test.jsx` is rewritten:

- a section is collapsed by default (its fields are not visible until the header is clicked);
- expanding a section reveals its fields in the grid; a `text` field is editable and calls
  `onSave` with the updated tree; a multi-line field spans full width;
- a multi-entry (list) section renders one collapsible sub-card per entry, each collapsed by
  default with a summary label;
- a locked section's fields are read-only and expose no feedback control;
- an unlocked section exposes a section-level 💬, and an unlocked entry exposes an entry-level 💬;
- no per-field 💬 is rendered.

`DocumentModal.test.jsx` is unchanged in contract (still branches tree-v1 → `DocumentTree`,
legacy → guard); adjust only if collapsed-by-default breaks an existing assertion.

## Part B — Configurable résumé page limit

### Storage (no migration)

The page limit lives in `profile.data.resume_max_pages`:

- integer N → cap the résumé at N pages (shrink-to-fit as today);
- `null` → unlimited (disables the shrink/limit);
- **absent → unlimited** (no limit). Existing profiles (which have no key) therefore render
  without a page cap until the user sets one — an intentional behavior change from today's
  hardcoded 1-page cap. No migration of existing rows.

**New profiles are seeded** with `resume_max_pages: 1` at creation, so a fresh profile defaults
to the 1-page limit (toggle on, value 1). The seed is written at profile-creation time (prefer
the backend create-profile seam for robustness; the frontend creation flow may set it if that is
the cleaner seam).

### Backend

Add a resolver that reads `profile.data.resume_max_pages` and returns `int | None`
(**absent → `None`/unlimited**; `null` → `None`; integer → that integer).
Replace the six hardcoded `max_pages=1` arguments with the resolved value so every résumé render
honors the setting:

- `core/job.py:735` (`write_resume_markdown` → render)
- `web/intake_pipeline.py:34`, `:279`, `:633` (generate, refine loop, feedback refine)
- `web/routers/jobs.py:567`, `:589` (PUT tree-v1 render, legacy/cover render)

The resolver reads from the same profile/User object those call sites already hold. `render_pdf`
already accepts `max_pages: int | None` where `None` disables the limit, so no change below the
call sites.

### Frontend (`ProfileDetail.jsx`)

Add a "Limit résumé length" control to the profile detail/editor:

- a **toggle** — off = unlimited, on = limited;
- a **1-character, digit-only text input** for the page count, shown/enabled when the toggle is on.

Toggle **off** persists `resume_max_pages: null`; toggle **on** persists the input's integer
value. Saved through the existing `updateProfile(profileId, { data })` path (the same mechanism
that stores `llm_model`, `resume_path`, etc.). The control **initializes from the stored value**:
an integer → toggle on with that number; `null` or absent → toggle off (unlimited). New profiles,
seeded with `1`, therefore open showing toggle on / `1`.

### Tests

- Backend: a test that `profile.data.resume_max_pages` flows into `generate_resume_pdf`'s
  `max_pages` — integer passes through, `null` → `None`, **absent → `None`** (mock `render_pdf` /
  `generate_resume_pdf` and assert the argument); plus a test that a newly created profile is
  seeded with `resume_max_pages: 1`.
- Frontend: a `ProfileDetail` test for the toggle + digit input persisting the right
  `resume_max_pages` value (if the suite has a harness for ProfileDetail; otherwise cover the
  pure read/normalize helper).

## Architecture / units

- **`DocumentTree.jsx`** — presentation only; consumes `FieldWidget` (`../profile-tree/
  fieldWidgets`) and the pure `docTreeOps` helpers (`setFieldValue`, `anchorLabel`,
  `sectionLocked`). New internal components: collapsible `SectionCard`, `GroupGrid`,
  `EntryCard`. No new external dependencies.
- **page-limit resolver** — a small pure function on the profile/User seam; single
  responsibility (read + normalize one setting), independently testable.
- **`ProfileDetail.jsx`** — gains one self-contained control bound to `profile.data`.

## Error handling

- A malformed `resume_max_pages` (non-integer string, ≤0) normalizes to the default (`1`); never
  crashes a render.
- An empty/whitespace digit input with the toggle on normalizes to `1` on save.
- DocumentTree rendering a section with no children or an entry with no fields renders an empty
  (but non-crashing) card.

## Out of scope

- Live in-dashboard PDF preview and user-customizable section templates — **sub-project #6**.
- Drag/reorder, add/remove, rename, lock/visibility in the document editor (those stay in the
  profile editor).
- Cover-letter editor changes.
- Per-document (per-job) page-limit overrides — the limit is a profile-level setting.
