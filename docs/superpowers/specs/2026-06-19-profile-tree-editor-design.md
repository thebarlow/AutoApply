# Profile Tree Editor (sub-project 2B) — Design

## Context

The "user-defined resume sections" initiative replaces the hardcoded 5-section
profile model with a user-definable schema tree. Sub-project **#1 (schema
engine)** made a recursive closed-vocabulary tree (`root → section →
list/group → field`) the source of truth in `core/profile_tree.py`, stored as
`profile_tree` JSON in `user_profile.data`. Sub-project **2A** consolidated all
write paths onto an ID-preserving in-place overlay and added tree-aware
endpoints: `GET`/`PUT /api/config/profiles/{id}/tree` (validated, ≤ 500 nodes,
≤ 6 deep, derives flat fields via `tree_to_legacy`, preserves non-section
metadata).

**2B** builds the **tree-driven profile editor** on top of those endpoints:
the dashboard renders and edits the profile *as a tree* — edit values, rename,
toggle visibility, reorder, remove, add list items, and add custom sections +
fields — replacing the hardcoded doc-section accordions in `ProfileDetail.jsx`.
The graphical drag-drop builder and recommended-section gallery are **2C**.

## Goals

- Render the whole profile tree generically from node `type`/`kind`, with
  kind-aware field widgets.
- Allow structural edits: add/remove list items, add/remove custom sections
  and fields, rename, reorder, toggle visibility.
- Persist via the 2A `PUT /tree` (whole-tree, validated), with explicit
  Save/Discard and a dirty indicator.
- Protect the preset role→flat mapping (`tree_to_legacy`) from
  schema-breaking edits.
- Retire the hardcoded doc-section editor UI in `ProfileDetail.jsx`.

## Non-goals (deferred)

- Drag-drop reorder, recommended-section gallery, graphical builder → **2C**.
- Rendering custom (`role is None`) sections on generated documents → **#4**.
- Editing LLM-gen attributes (`llm_output`, `llm_input`, `llm_instructions`,
  `regen_lock`) and bullet bounds (`min`/`max`) / `bullet_style` → preserved
  untouched via the tree round-trip; no editing UI in 2B.
- Removing the flat `update_profile` endpoint (see "Retirement" — it still
  serves name, job-preferences, and onboarding).

## Decisions (resolved during brainstorming)

1. **Structural scope:** 2B may add list items **and** custom sections +
   fields (via plain forms/buttons, no drag-drop). Drag-drop + gallery → 2C.
2. **Render strategy:** generic recursive renderer + a few kind-specific field
   widgets (taglist → chip input, markdown → textarea, bullets → line list,
   text → input). Sections/lists render uniformly.
3. **Save model:** explicit Save button (whole-tree `PUT /tree`) + dirty
   indicator + Discard.
4. **Editable attributes in 2B:** node **name**, field **value**, **visible**
   toggle, and **field kind** on newly added custom fields. Everything else
   round-trips untouched.
5. **Flat PUT fate:** keep `update_profile` for name, job-preferences
   (target roles/salary), and onboarding upload-attach. 2B retires only the
   flat *doc-section editor UI*, not the endpoint.

## Architecture

New directory `react-dashboard/src/components/widgets/profile-tree/`.

### Components

- **`ProfileTreeEditor.jsx`** — top-level. On mount, `GET
  /api/config/profiles/{id}/tree`; holds `{tree, dirty, error}` in immutable
  React state. Renders the section list + a sticky **Save / Discard** bar.
  Owns `update(nodeId, mutator)` which returns a new tree with the target node
  replaced (structural sharing) and sets `dirty`. Save → `PUT /tree`.
- **`TreeNode.jsx`** — recursive dispatcher on `node.type` →
  Section/Group/List/Field sub-renderers. Pure function of node + callbacks
  (`onChange`, `onRename`, `onToggleVisible`, `onRemove`, `onMoveUp`,
  `onMoveDown`, `onAddItem`, `onAddField`, `onAddSection`).
- **`fieldWidgets.jsx`** — kind-aware editors, each `(value, onChange)`:
  - `text` → single-line input
  - `markdown` → textarea
  - `bullets` → editable line list (add/edit/remove lines) → `string[]`
  - `taglist` → chip input (reuse existing skill-chip pattern) → `string[]`
- **`structuralControls.jsx`** — shared small controls: move ↑/↓, visible
  eye-toggle, inline-editable rename label, remove (✕ with confirm), and
  "+ Add" affordances (item / field / section).

Each unit is independently testable: widgets take `(value, onChange)`;
structural controls take callbacks; `TreeNode` is a pure render of node +
handlers; `ProfileTreeEditor` owns all I/O and state.

### Rendering rules — preset vs custom provenance

`tree_to_legacy` maps preset sections by `role` and their fields by `key`. To
protect that mapping, behavior is driven by provenance (data-driven, not
per-section hardcoding):

**Preset sections** (`role in {header, summary, experience, education,
projects, skills}`):
- Display **name**: renamable (cosmetic; `role`/`key` untouched).
- **Visible** toggle: allowed.
- **Reorder**: allowed (updates `order` only).
- **Remove**: not rendered — use the visible toggle to hide instead (delete
  would silently drop the role mapping).
- Fields: **values editable**; field add/remove/rename **disabled** on preset
  groups (keys are contractually mapped). For preset **list** sections
  (experience/education/projects), **items** may be added/removed/reordered;
  the per-item field set is fixed (new items cloned from `item_template`).

**Custom sections** (`role is None`):
- Full control: rename, visible, reorder, remove, add/remove/rename fields,
  choose field **kind** on add, add/remove/reorder items in custom lists.

**Field-kind picker:** shown only when adding a *new* custom field
(text/markdown/bullets/taglist); existing fields' kind is fixed in 2B.

**Reorder:** up/down buttons only (drag-drop is 2C). A move/add/remove
renormalizes the affected sibling list's `order` to `0..n-1` (gap-free,
unique) before the new tree lands in state, so the server's `validate_tree`
never rejects a benign reorder.

### State, save & validation

- **Local state:** immutable tree in React state; all edits via
  `update(nodeId, mutator)`; children never mutate, only invoke callbacks.
  Node identity uses the stable `id` from 2A.
- **Order maintenance:** add/remove/move renormalize sibling `order` locally
  to satisfy the tree's order invariant before save.
- **Save:** `PUT /api/config/profiles/{id}/tree` with `{tree}`. On 200,
  replace local state with the server's canonicalized returned tree and clear
  `dirty`. On **422**, keep local edits and surface the server's validation
  detail inline near the Save bar (e.g. node/depth cap, duplicate id). On
  network error, keep `dirty` and show a retryable error. The editor never
  silently drops edits.
- **Discard:** revert local tree to the last loaded/saved snapshot; clear
  `dirty`.
- **Dirty guard:** leaving the editor (switching profile tab / closing) while
  `dirty` prompts a confirm (mirroring any existing unsaved-edit pattern;
  otherwise a simple in-SPA confirm).

### Integration & API surface

- **`ProfileDetail.jsx`:** remove the hardcoded doc-section accordions
  (Identity/Profile, Contact, Skills, Experience, Education, Projects and their
  `isSectionEmpty`/edit-modal helpers) and render a single
  `<ProfileTreeEditor profileId={...} />` in their place. **Retained
  untouched:** profile **name**, **Job Preferences** (target roles/salary, via
  `update_profile`), **Prompts** accordion, **LLM Config** accordion. This
  shrinks the 1559-line `ProfileDetail` and isolates the tree concern.
- **`api.js`:** add `getProfileTree(id)` and `putProfileTree(id, tree)` (the
  only new API wrappers). `updateProfile` stays for name/preferences/
  onboarding.

### Retirement

The bespoke doc-section components/helpers in `ProfileDetail` that only served
section editing are deleted (no dead code). The flat `update_profile` endpoint
and its other callers (Settings name, StepResume onboarding, api.js metadata
helper) are **unchanged**. The roadmap's "retire flat PUT" is reinterpreted as
"retire the flat doc-section editor UI" — recorded here so the constraint is
explicit and the endpoint's continued role is documented.

### Onboarding interaction

Manual-entry onboarding (`auto-apply:edit-profile` → opens the editor) now
lands in the tree editor. Entering experience/education/skills still flips
`setup-status` `resume_parsed` true, since that flag derives from profile-data
presence, which the tree round-trips to flat. This path is verified in
testing.

## Testing

**Test-harness setup (new):** the React dashboard currently has **no** frontend
test infrastructure (no Vitest/Jest, no React Testing Library, no test files —
the repo's only tests are Python/pytest). 2B introduces the first frontend
harness: add **Vitest + React Testing Library + jsdom** as dev deps, a `test`
script in `react-dashboard/package.json`, and minimal Vitest config + setup
file. This is the project's first frontend test suite and is part of 2B's
scope (one early task).

**Component tests** (Vitest + React Testing Library):
- `fieldWidgets`: each kind — text/markdown edit emits string; bullets
  add/edit/remove emits `string[]`; taglist chip add/remove emits `string[]`;
  empty states.
- `structuralControls`: move ↑/↓ disabled at list ends; remove fires confirm;
  rename commits on blur/Enter, cancels on Escape.
- `TreeNode`: preset section renders no remove button and a locked field-set;
  custom section renders full controls; list renders add/remove item; visible
  toggle flips state.
- `ProfileTreeEditor`: loads tree from mocked `GET`; an edit sets dirty; Save
  PUTs the exact tree and clears dirty; 422 keeps edits and shows the server
  message; Discard reverts; order renormalization after move/remove.

**Backend:** no new endpoints; rely on 2A's endpoint tests. One optional
integration assertion that a tree round-tripped through the editor's PUT
preserves a custom section and a preset's flat mapping.

**Error handling:** 422 (validation/caps), network failure (retryable), and an
empty/legacy profile (GET migrates on first access and returns a valid preset
tree the editor renders).

## Risks

- **Schema-protection gaps:** if a provenance rule is wrong (e.g. a preset
  becomes deletable), a save could drop a role mapping. Mitigated by
  data-driven provenance rules + 2A's server-side `validate_tree` and the
  preserved-mapping integration test.
- **Two save scopes in one view:** tree (dirty/PUT) vs flat metadata
  (`update_profile`). Kept independent; documented so users/devs aren't
  surprised that name/preferences save separately from the tree.
- **Order invariant:** client must renormalize sibling `order` on every
  structural op or the server 422s a benign reorder. Covered by an explicit
  `ProfileTreeEditor` test.
