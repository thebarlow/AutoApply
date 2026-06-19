# Profile Tree-Edit Foundation (2A) — Design Spec

**Date:** 2026-06-19
**Status:** Approved (brainstorming complete; pending implementation plan)
**Sub-project:** #2, phase A of the "user-defined resume sections" initiative

## Background

Sub-project #1 (the Profile Schema Engine, merged locally to `main`) made a
recursive typed tree (`root → section → list/group → field`, `core/profile_tree.py`)
the source of truth for profile structure, stored as `profile_tree` JSON in
`user_profile.data`. Legacy flat attributes are derived from the tree on load
via `tree_to_legacy`. See `core/CONTEXT.md` → "Profile Schema Engine".

#1 left a documented prerequisite (finding I1): `User._to_dict` calls
`with_rebuilt_tree`, which **discards the entire tree and regenerates every node
ID** from the flat fields on every `user.save()`. This is safe only while the
flat fields are the sole input. The moment users author tree-only structure
(custom sections, regen locks, ordering — sub-project #2C), any `user.save()`
from a flat writer (the legacy profile editor, `web/routers/skills.py` mutating
`user.skills`) would silently destroy that structure.

Sub-project #2 (the builder UI) is phased: **2A — backend tree-edit foundation
(this spec)**, 2B — tree-driven profile editor, 2C — graphical custom-section
builder + recommended gallery. 2A locks the API contract and fixes I1 before any
UI work begins.

## Goal

Deliver a backend foundation where the tree can be read and written as a tree,
node IDs and tree-only data survive every write path, and the existing flat
editor keeps working unchanged. No dashboard changes in 2A.

## Non-goals (later phases)

- Any dashboard/UI change — rendering the tree, editing values, rename/reorder/
  remove (2B); the drag-and-drop custom-section builder + recommended gallery
  (2C).
- Schema-driven LLM generation against custom sections (#3) and rendering them
  on documents (#4). Custom sections remain storable-but-not-rendered.
- Multi-writer concurrency control (versioning / optimistic locking). Single
  account = single profile; lost-update risk is low and explicitly deferred.

## Design

### 1. Tree API — the new write path

Two endpoints in `web/routers/config.py`, scoped to the caller's tenant
(`current_profile_id`, same guard as the existing profile endpoints):

- **`GET /api/config/profiles/{id}/tree`** → `{ "tree": <profile_tree JSON> }`.
  Resolves via `User.load` so a profile with no stored tree is migrated
  (`legacy_to_tree`) and persisted, exactly as a normal load. Returns the
  validated tree.

- **`PUT /api/config/profiles/{id}/tree`** ← `{ "tree": <full tree JSON> }`.
  Server pipeline:
  1. `RootNode.model_validate(body.tree)` — structural/type validation.
  2. Size/shape caps (§3) — reject oversized trees.
  3. `validate_tree(root)` — invariants (unique IDs, sibling order, item
     conformance, etc.). On failure → HTTP 422 with the validation message.
  4. **Preserve client-supplied node IDs verbatim** — no regeneration. New nodes
     created in the client carry client-minted UUIDs; uniqueness is enforced by
     `validate_tree`.
  5. Derive flat fields via `tree_to_legacy`, merge with preserved non-section
     metadata from the existing stored `data` (target roles/salary, resume/md
     paths, LLM config, uploaded-file fields), and store **both** the flat fields
     and `profile_tree` in `user_profile.data`.
  6. Returns the stored tree.

No dashboard code calls these endpoints in 2A; they are the contract 2B
consumes and are exercised by tests (mirroring how #1's adapter shipped
test-only).

### 2. The I1 fix — in-place flat overlay

Replace the `with_rebuilt_tree` call in `User._to_dict` with a new function
`apply_flat_to_tree(existing_tree: RootNode, flat: dict) -> RootNode` in
`core/profile_tree.py`. It **overlays** the flat fields onto the existing tree
rather than rebuilding it:

- **Scalar role-mapped fields** (header contact fields, summary/`hero`, the flat
  `skills` taglist): located by `(section.role, field.key)` and updated in place,
  preserving each node's ID.
- **List sections** (`experience`/`education`/`projects`): matched to the flat
  list (`work_history`/`education`/`projects`) **by index**:
  - Index `i` that exists in both → update that item group's field values in
    place, preserving the group's and fields' IDs.
  - Indices beyond the existing items → append new item groups (cloned from the
    list's `item_template`, fresh IDs) populated from the flat rows.
  - Existing items beyond the flat list length → removed.
- **Anything the flat fields do not describe is left untouched**: custom
  (`role is None`) sections, `regen_lock`, `llm_output`/`llm_input`/
  `llm_instructions`, `visible`, `bullet_style`, and the structure/IDs of all
  role-mapped nodes that still exist.

After overlay, `validate_tree` runs (defensively) and `section_order`/structure
is unchanged. First-load migration of a profile with no tree still uses
`legacy_to_tree` (in `_hydrate`); `apply_flat_to_tree` is only used on save when
a tree already exists.

`with_rebuilt_tree` is removed (its two callers — the legacy flat `PUT
/profiles/{id}` and `User.load_from_json` — switch to the overlay path: load or
migrate the existing tree, then `apply_flat_to_tree`). The net effect is that
**every** write path is now ID-preserving and tree-structure-preserving.

### 3. Validation & limits

`PUT /tree` enforces, in addition to `model_validate` + `validate_tree`:
- **Node count cap:** ≤ 500 total nodes.
- **Depth cap:** ≤ 6 levels from root.

A new `validate_tree_limits(root, *, max_nodes=500, max_depth=6)` (or parameters
threaded into a wrapper) raises a `TreeValidationError`; the endpoint maps any
`TreeValidationError` to HTTP 422 with the message. These caps prevent a
malformed or abusive client tree from causing unbounded work on later loads.
Inputs are otherwise machine-generated by the 2B/2C UI.

### 4. Coexistence

- Legacy `PUT /api/config/profiles/{id}` (flat) is retained and now
  ID-preserving via the overlay. It is retired in 2B.
- The tree endpoints are purely additive.
- `_hydrate` (derive flat from tree on load) is unchanged.
- No dashboard behavior changes in 2A.

## Files touched

- `core/profile_tree.py` — add `apply_flat_to_tree`; add tree size/depth limit
  validation; remove `with_rebuilt_tree` (or reduce it to a thin wrapper that
  migrates-then-overlays for the no-existing-tree case, used by `load_from_json`).
- `core/user.py` — `_to_dict` and `load_from_json` use the overlay path instead
  of `with_rebuilt_tree`.
- `web/routers/config.py` — add `GET`/`PUT /api/config/profiles/{id}/tree`;
  flat `update_profile` switches to the overlay path.
- Tests: `tests/core/test_profile_tree.py`, `tests/core/test_user.py`, and a web
  test for the tree endpoints.

The `src/api.js` client wrappers (`getProfileTree`/`putProfileTree`) are
**deferred to 2B**, where they are wired into the editor. 2A is backend-only.

## Testing

- **I1 regression (primary):** build a tree with a custom (`role=null`) section
  and a node with `regen_lock=true`; mutate a flat attr (`user.skills`,
  `user.work_history`) and `user.save()`; reload — the custom section and the
  regen lock survive, and role-mapped node IDs are unchanged.
- **Flat overlay value/shape:** updating a scalar field changes its value
  (ID preserved); appending a flat work-history row adds an item group; removing
  a row drops the tail item; surviving items keep their IDs.
- **Tree PUT round-trip:** GET tree → modify a field value + add a custom section
  with a client UUID → PUT → GET — IDs preserved, custom section present, flat
  fields (`GET /profiles/{id}`) reflect the role-mapped edits.
- **PUT validation:** malformed tree (bad type / duplicate ID / non-conforming
  list item) → 422; oversized tree (> node/depth cap) → 422.
- **Generation consistency:** after a tree PUT, `User.load` derives the expected
  `work_history`/`skills`/etc., so the existing generation/assembler path is
  unaffected (assert derived legacy attrs match the tree).

## Open risk / deferred

- Concurrency (two writers, lost update) is deferred — single-user-per-profile.
  A future `updated_at`/version precondition can be added without changing the
  contract.
- Index-based matching in `apply_flat_to_tree` is lossy for a reorder performed
  through the *flat* path (it would shuffle which tree item an ID maps to). This
  is acceptable: the flat editor performs no reorder and is retired in 2B, after
  which all structural edits go through the ID-preserving tree PUT.
