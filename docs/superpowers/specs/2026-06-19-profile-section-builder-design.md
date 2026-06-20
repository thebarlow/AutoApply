# Profile Section Builder (2C) — Design

**Sub-project 2C** of the "user-defined resume sections" initiative. Adds a
graphical drag-drop reordering experience and a recommended-section gallery on
top of the 2B tree-driven profile editor. Pure frontend: no backend or API
changes; persistence remains the whole-tree `PUT /api/config/profiles/{id}/tree`
from 2A/2B.

## Roadmap context

- **2A** (write-path + tree API) — DONE, merged to local `main`.
- **2B** (tree-driven editor) — DONE, merged to local `main`. Generic editor in
  `react-dashboard/src/components/widgets/profile-tree/`; sections collapse by
  default; up/down (`↑`/`↓`) reorder buttons; plain add-forms; tag-chip alias
  modal. First frontend test suite (Vitest + RTL).
- **2C** (this spec) — drag-drop reorder + recommended-section gallery. 2B
  deliberately deferred both to here.
- **#3** schema-driven LLM generation, **#4** schema-driven rendering (until #4
  ships, custom sections are storable/editable but do NOT appear on generated
  documents), **#5** onboarding parse.

**RELEASE CONSTRAINT:** do NOT push `main` until the whole initiative (through
#5) is complete. Each sub-project merges to LOCAL `main` only. Start 2C on a
feature branch off `main`; on completion merge to local `main` (no push).

## Goals

1. **Drag-drop reordering** of **sections** (root children) and **list items**
   (entries within a list, e.g. work history), using `dnd-kit`. The existing
   `↑`/`↓` buttons are **retained** as the keyboard/touch/accessibility
   fallback. Fields within custom groups are **not** drag-reorderable in 2C
   (they keep `↑`/`↓` only).
2. **Recommended-section gallery**: a card picker that replaces 2B's plain
   "+ Add section" button. Clicking a card inserts a fully-editable `role:null`
   custom section pre-shaped from a static template.

## Non-goals (2C)

- No backend/API changes, no new endpoints, no schema changes.
- No field-level drag-drop (fields within custom groups).
- No intelligent/data-driven recommendations — the gallery is a fixed catalog.
- No rendering of custom sections on generated documents (that is #4).

## Global constraints (carried from 2A/2B)

- The profile **tree** is the source of truth; the editor persists only via the
  whole-tree `PUT`. Reorder/add produce a new tree → dirty → existing Save.
- Server invariants the client must keep (else PUT 422s): unique node ids;
  unique group field keys; section has exactly one child; list items match the
  `item_template` `(key, kind)` shape; `order` unique and renormalized to
  `0..n-1` among Root/Section/List children after every change; ≤ 500 nodes,
  ≤ 6 levels deep.
- Field `value` types by `kind`: `text`/`markdown` → string; `bullets`/`taglist`
  → array of strings.
- New nodes get fresh ids via `crypto.randomUUID()` (`treeOps.newId`).
- Tree-only attrs (`llm_output`, `llm_input`, `llm_instructions`, `regen_lock`,
  `bullet_style`, `min`, `max`) carry their defaults on built nodes and
  round-trip untouched thereafter.
- JS style matches the dashboard (ES modules, function components, hooks,
  Tailwind, the shared `inputClass` look). Commit format `[type] Imperative
  subject`. No Claude/Anthropic attribution.
- Each unit gets failing-test-first coverage; `npm run test` from
  `react-dashboard/` stays green.

## Node JSON shapes (must match the server, per 2A/2B)

- section: `{type:'section', id, name, role, order, visible, children}`
- list: `{type:'list', id, name, order, visible, bullet_style, item_template, children}`
- group: `{type:'group', id, name, order, visible, regen_lock, children}`
- field: `{type:'field', id, name, key, order, visible, kind, value, llm_output, llm_instructions, llm_input, regen_lock, min, max}`

## Recommended-section catalog (locked: 7 + Blank)

Each template builds a `role:null` (custom) section, fully editable after
insertion. `key`s are slugified from field names (`treeOps.slugify`), unique
within their group. List templates start with **one empty item** (cloned from
the item template) so fields are visible on expand. Taglist templates are a
single field with empty `[]` value.

| Template | Section child | Item / field shape |
|---|---|---|
| Certifications | list | item: Name (text), Issuer (text), Date (text) |
| Awards & Honors | list | item: Title (text), Issuer (text), Year (text) |
| Publications | list | item: Title (text), Venue (text), Year (text), URL (text) |
| Volunteer Experience | list | item: Organization (text), Role (text), Dates (text), Description (markdown) |
| Languages | single field | taglist |
| Courses | single field | taglist |
| Interests | single field | taglist |
| Blank | one empty group | — (today's "+ Add section") |

List sections: `bullet_style: 'none'`; the section's single child is a `list`
whose `item_template` is a `group` of the listed fields (empty values) and whose
`children` is one fresh clone of that template (fresh ids, empty values).

## Architecture

New/changed files in `react-dashboard/src/components/widgets/profile-tree/`:

### `sectionCatalog.js` (new, pure)
- `SECTION_TEMPLATES` — array of `{ id, label, description, build() }` template
  specs (the 8 above). `description` is a short gallery-card subtitle.
- `buildSectionFromTemplate(template) -> SectionNode` — mints the section
  subtree per the table: fresh UUIDs throughout, correct `kind`s, `order`s set,
  all tree-only attrs at their defaults, list templates seeded with one empty
  item. Reuses `treeOps.newId`/`makeField`/`slugify` where natural.

Fully unit-tested without rendering.

### `treeOps.js` (additions, pure)
- `reorderSiblings(tree, activeId, overId) -> tree` — locate the sibling array
  containing `activeId`; if `overId` is in the **same** array, move `active` to
  `over`'s index and `renumber`; otherwise (different container, or either id
  not found) return the tree unchanged (no-op). Recurses through `children`
  only (never `item_template`). Serves both section reorder and list-item
  reorder.
- `addSection(tree, sectionSubtree) -> tree` — append a prebuilt section to root
  and `renumber` root children. `addCustomSection(tree, name)` is refactored to
  build the Blank subtree and delegate to `addSection` (behavior unchanged).

### `SectionGallery.jsx` (new, presentational)
- `SectionGallery({ templates, onAdd })` — a collapsed "+ Add section" button
  that expands into a grid of cards (one per template, including Blank). Each
  card shows `label` + `description`; clicking it calls `onAdd(template)` and
  collapses the panel. Dumb/callback-driven.

### Drag-drop wiring (dnd-kit)
Dependencies added to `package.json`: `@dnd-kit/core`, `@dnd-kit/sortable`,
`@dnd-kit/utilities`.

To keep `SectionView` unit-testable in isolation (2B tests render it directly,
outside any DnD provider), DnD is wired **around** the presentational
components, not inside `SectionView`:

- `SectionView` gains an **optional** `dragHandle` prop (a render node) shown
  beside the collapse caret. When absent (its 2B unit tests), nothing changes.
- **Sections**: `ProfileTreeEditor` wraps the section list in a `DndContext`
  (PointerSensor + KeyboardSensor) + vertical `SortableContext` over section
  ids. A thin `SortableSection` wrapper calls `useSortable({ id: section.id })`,
  applies the sortable ref/transform, and renders
  `<SectionView dragHandle={<handle…/>} … />`. `onDragEnd` →
  `ops.reorder(active.id, over.id)`.
- **List items**: `ListView` owns its **own** `DndContext` + `SortableContext`
  over its item ids (so items reorder only within their list, never across
  sections). Each entry renders through a `SortableItem` wrapper supplying that
  entry's drag handle. `onDragEnd` → `ops.reorder(active.id, over.id)`.
  Because `ListView` provides its own provider, 2B's `TreeNode` tests (which
  render `SectionView` → `ListView`) still mount cleanly.

### `ProfileTreeEditor.jsx` (changes)
- Add `reorder: (activeId, overId) => setTree(t => reorderSiblings(t, activeId, overId))`
  to the `ops` bundle (existing `move(id, ±1)` stays for the `↑`/`↓` buttons).
- Replace the inline "+ Add section" button with `<SectionGallery>`; its
  `onAdd(template)` → `setTree(t => addSection(t, buildSectionFromTemplate(template)))`.
- Wrap the rendered sections in the sections-level `DndContext`/`SortableContext`
  via `SortableSection`.

## Data flow

Drag end / gallery add → new tree object → `dirty` true → user clicks Save →
existing whole-tree `PUT` → state replaced with the server's canonical tree.
`renumber` keeps `order` contiguous, so no new 422 surface is introduced.

## Error handling

- `reorderSiblings` no-ops on cross-container or unknown ids (defensive; dnd-kit
  shouldn't emit those given per-container `SortableContext`s, but the reducer
  must not corrupt the tree if it does).
- Gallery insertion can't fail client-side; any server rejection surfaces
  through 2B's existing 422 handling on Save.

## Testing

- **`sectionCatalog.test.js`** — for each template: built section is
  `role:null`; child type matches (list/field/group); field `kind`s correct;
  every node id is fresh and unique; list templates have a matching
  `item_template` plus exactly one empty seeded item with empty values and
  template-matching keys; taglist templates have a single `[]`-valued field;
  Blank has one empty group.
- **`treeOps.test.js`** (additions) — `reorderSiblings` reorders sections;
  reorders list items within a list; is a no-op across containers and for
  unknown ids; `renumber` invariant holds. `addSection` appends + renumbers;
  `addCustomSection` still yields the Blank shape via `addSection`.
- **`SectionGallery.test.jsx`** — renders all 8 cards; the panel toggles open;
  clicking a card calls `onAdd` with that template.
- **`ProfileTreeEditor.test.jsx`** (additions) — adding a gallery template (e.g.
  Certifications) inserts the section (its header appears); `ops.reorder` wired.
- **DnD** — the reorder logic is exercised through `reorderSiblings` directly;
  the dnd-kit wiring is kept thin (simulating pointer drags in jsdom is
  brittle, so tests do not depend on it). A light assertion confirms a section
  drag handle renders (`aria-label` "Drag to reorder section").

## Out of scope / deferred

- Field-level drag-drop; cross-section item moves; gallery search/filtering;
  data-driven recommendations; document rendering of custom sections (#4).
