# Profile Section Builder (2C) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add drag-drop reordering (sections + list items) and a recommended-section gallery to the 2B tree-driven profile editor.

**Architecture:** Pure-frontend additions to `react-dashboard/src/components/widgets/profile-tree/`. New pure helpers (`reorderSiblings`, `addSection` in `treeOps.js`; `sectionCatalog.js` with template builders) are unit-tested without rendering. A presentational `SectionGallery` replaces 2B's "+ Add section" button. Drag-drop is wired with `dnd-kit` **around** the existing presentational components — `SectionView` gains an optional `dragHandle` prop; `ProfileTreeEditor` wraps sections in a `DndContext`/`SortableContext`; `ListView` owns its own per-list `DndContext` — so 2B's component unit tests stay valid. The existing `↑`/`↓` buttons are retained as the keyboard/touch fallback; persistence stays the whole-tree `PUT` from 2A/2B.

**Tech Stack:** React 18, Vite 5, Vitest, React Testing Library, jsdom, Tailwind, `@dnd-kit/core` + `@dnd-kit/sortable` + `@dnd-kit/utilities`.

## Roadmap Context (read first — this plan starts a fresh session)

This is **sub-project 2C** of the "user-defined resume sections" initiative:
replace the hardcoded 5-section résumé model with a user-definable schema tree.
The full roadmap + cold-start facts live in the auto-memory
`project-profile-schema-engine` (load it first) and in `core/CONTEXT.md` →
"Profile Schema Engine". The recursive tree (`root → section → list/group →
field`) is the profile source of truth in `core/profile_tree.py`.

**Sub-project sequence (each gets its own spec → plan → impl → merge-to-local-`main` cycle):**
1. **Schema engine** — DONE, merged to local `main`.
2. **Builder UI** — phased:
   - **2A** (write-path + tree `GET`/`PUT /api/config/profiles/{id}/tree`) — DONE, merged.
   - **2B** (tree-driven profile editor) — DONE, merged. Generic editor in
     `react-dashboard/src/components/widgets/profile-tree/`; sections collapse by
     default; `↑`/`↓` reorder buttons; tag-chip alias modal. First frontend test
     suite (Vitest + RTL, `npm run test` from `react-dashboard/`).
   - **2C** (THIS PLAN) — drag-drop reorder (sections + list items) + recommended-
     section gallery, on the 2B editor. Spec:
     `docs/superpowers/specs/2026-06-19-profile-section-builder-design.md`.
3. **Schema-driven LLM generation** against custom sections (next after 2C).
4. **Schema-driven rendering** of custom sections on documents. **Until #4 ships,
   custom sections are storable/editable but do NOT appear on generated
   résumés/cover letters.**
5. **Onboarding parse** that maps novel sections.

**RELEASE CONSTRAINT:** do NOT push `main` until the ENTIRE initiative (through
#5) is complete. Each sub-project merges to LOCAL `main` only.

**Before starting 2C:** create a feature branch off `main`
(`git checkout -b feat/profile-section-builder`). On completion, use
`superpowers:finishing-a-development-branch` → merge to local `main` (no push).

**After 2C lands (do this before context-clearing for #3):**
1. Update the `project-profile-schema-engine` auto-memory: mark 2C DONE (with its
   commit range), set CURRENT STATE to "2C done, NEXT: brainstorm→spec→plan→impl
   #3 (schema-driven LLM generation)".
2. Then continue the roadmap in order: **#3 → #4 → #5**, each via
   brainstorm (superpowers:brainstorming) → spec → writing-plans → subagent-driven
   -development, all on a fresh feature branch off `main`, merged to local `main`
   only. Do not push until #5 is done.

## Global Constraints

- The profile **tree** is the source of truth; the editor persists only via `PUT /api/config/profiles/{id}/tree`. Reorder/add produce a new tree → dirty → existing Save. No backend/API changes in 2C.
- Server invariants the client MUST keep (else PUT 422s): every node `id` unique tree-wide; a group's child field `key`s unique within the group; a section has **exactly one** child; list items match the `item_template` `(key, kind)` shape; among Root/Section/List children, `order` is unique and renormalized to `0..n-1` after every change; ≤ 500 nodes, ≤ 6 levels deep.
- Field `value` types by `kind`: `text`/`markdown` → string; `bullets`/`taglist` → array of strings.
- New nodes get fresh ids via `crypto.randomUUID()` (`treeOps.newId`).
- Tree-only attrs (`llm_output`, `llm_input`, `llm_instructions`, `regen_lock`, `bullet_style`, `min`, `max`) carry their defaults on built nodes and round-trip untouched thereafter.
- Node JSON shapes (match the server): section `{type:'section', id, name, role, order, visible, children}`; list `{type:'list', id, name, order, visible, bullet_style, item_template, children}`; group `{type:'group', id, name, order, visible, regen_lock, children}`; field `{type:'field', id, name, key, order, visible, kind, value, llm_output, llm_instructions, llm_input, regen_lock, min, max}`.
- JS style matches the dashboard (ES modules, function components, hooks, Tailwind, the shared `inputClass` look). Commit format `[type] Imperative subject`; types `feat|fix|refactor|docs|test|chore`. No Claude/Anthropic attribution, no `Co-Authored-By`.
- Tests run with `npm run test` from `react-dashboard/`. Each task: failing test → run → implement → run green → commit.

## File Structure

- **Modify** `react-dashboard/src/components/widgets/profile-tree/treeOps.js` — export `cloneWithFreshIds`; add `addSection`, `reorderSiblings`; refactor `addCustomSection`.
- **Modify** `.../profile-tree/treeOps.test.js` — tests for the new helpers.
- **Create** `.../profile-tree/sectionCatalog.js` + `sectionCatalog.test.js` — the 7 + Blank templates and `buildSectionFromTemplate`.
- **Create** `.../profile-tree/SectionGallery.jsx` + `SectionGallery.test.jsx`.
- **Modify** `.../profile-tree/ProfileTreeEditor.jsx` + `ProfileTreeEditor.test.jsx` — `reorder` op, `<SectionGallery>`, section-level `DndContext`.
- **Modify** `.../profile-tree/TreeNode.jsx` + `TreeNode.test.jsx` — `SectionView` `dragHandle` prop; `ListView` per-list `DndContext`.
- **Modify** `react-dashboard/package.json` — dnd-kit deps.
- **Modify** `react-dashboard/CONTEXT.md`, `core/CONTEXT.md` — document 2C.

---

### Task 1: Pure tree helpers — `addSection`, `reorderSiblings`, export `cloneWithFreshIds`

**Files:**
- Modify: `react-dashboard/src/components/widgets/profile-tree/treeOps.js`
- Modify: `react-dashboard/src/components/widgets/profile-tree/treeOps.test.js`

**Interfaces:**
- Consumes: existing `renumber`, `newId`, `cloneWithFreshIds` (internal), `addCustomSection`.
- Produces:
  - `export function cloneWithFreshIds(node) -> node` — was internal; now exported (deep-clone with fresh ids, used by `sectionCatalog`).
  - `addSection(tree, sectionSubtree) -> tree` — append a prebuilt section to root and renumber root children.
  - `reorderSiblings(tree, activeId, overId) -> tree` — move `activeId` to `overId`'s index **within the same sibling array**; renumber. No-op if the ids are in different containers or either id is absent, or if `activeId === overId`.
  - `addCustomSection(tree, name) -> tree` — unchanged behavior, now delegates to `addSection`.

- [ ] **Step 1: Write the failing tests**

Add to `react-dashboard/src/components/widgets/profile-tree/treeOps.test.js` (append inside the file, after the existing imports add the new names, and add these `describe` blocks at the end):

Update the import line at the top of the file to include the new exports:

```js
import {
  PRESET_ROLES, isPresetSection, renumber, updateNode, removeNode,
  moveNode, makeField, addField, addListItem, addCustomSection,
  cloneWithFreshIds, addSection, reorderSiblings,
} from './treeOps'
```

Append these describes at the end of the file:

```js
describe('cloneWithFreshIds', () => {
  it('deep-clones with fresh ids and preserves values + item_template', () => {
    const node = {
      type: 'list', id: 'l', name: 'L', order: 0, visible: true, bullet_style: 'none',
      item_template: { type: 'group', id: 'tmpl', name: 'I', order: 0, visible: true,
        regen_lock: false, children: [
          { type: 'field', id: 'tf', name: 'A', key: 'a', order: 0, visible: true,
            kind: 'text', value: '' }] },
      children: [{ type: 'group', id: 'g0', name: 'I', order: 0, visible: true,
        regen_lock: false, children: [
          { type: 'field', id: 'f0', name: 'A', key: 'a', order: 0, visible: true,
            kind: 'text', value: 'keep' }] }],
    }
    const clone = cloneWithFreshIds(node)
    expect(clone.id).not.toBe('l')
    expect(clone.item_template.id).not.toBe('tmpl')
    expect(clone.children[0].id).not.toBe('g0')
    expect(clone.children[0].children[0].id).not.toBe('f0')
    expect(clone.children[0].children[0].value).toBe('keep') // values preserved
  })
})

describe('addSection', () => {
  it('appends a prebuilt section and renumbers root children', () => {
    const tree = { type: 'root', id: 'r', children: [
      { type: 'section', id: 's0', name: 'A', role: 'skills', order: 0, visible: true, children: [] },
    ] }
    const sec = { type: 'section', id: 's1', name: 'B', role: null, order: 99, visible: true, children: [] }
    const next = addSection(tree, sec)
    expect(next.children).toHaveLength(2)
    expect(next.children[1].id).toBe('s1')
    expect(next.children.map((c) => c.order)).toEqual([0, 1])
  })
})

describe('addCustomSection (via addSection)', () => {
  it('still appends a role:null section with one empty group', () => {
    const tree = { type: 'root', id: 'r', children: [] }
    const next = addCustomSection(tree, 'Awards')
    expect(next.children).toHaveLength(1)
    const sec = next.children[0]
    expect(sec.role).toBeNull()
    expect(sec.name).toBe('Awards')
    expect(sec.children).toHaveLength(1)
    expect(sec.children[0].type).toBe('group')
    expect(sec.children[0].children).toHaveLength(0)
    expect(sec.order).toBe(0)
  })
})

describe('reorderSiblings', () => {
  function tree() {
    return { type: 'root', id: 'r', children: [
      { type: 'section', id: 'a', name: 'A', role: null, order: 0, visible: true, children: [
        { type: 'list', id: 'la', name: 'L', order: 0, visible: true, bullet_style: 'none',
          item_template: { type: 'group', id: 't', name: 'I', order: 0, visible: true, regen_lock: false, children: [] },
          children: [
            { type: 'group', id: 'i0', name: 'I', order: 0, visible: true, regen_lock: false, children: [] },
            { type: 'group', id: 'i1', name: 'I', order: 1, visible: true, regen_lock: false, children: [] },
            { type: 'group', id: 'i2', name: 'I', order: 2, visible: true, regen_lock: false, children: [] },
          ] }] },
      { type: 'section', id: 'b', name: 'B', role: null, order: 1, visible: true, children: [] },
      { type: 'section', id: 'c', name: 'C', role: null, order: 2, visible: true, children: [] },
    ] }
  }

  it('reorders root sections and renumbers', () => {
    const next = reorderSiblings(tree(), 'c', 'a') // move C to A's slot
    expect(next.children.map((s) => s.id)).toEqual(['c', 'a', 'b'])
    expect(next.children.map((s) => s.order)).toEqual([0, 1, 2])
  })

  it('reorders list items within their list', () => {
    const next = reorderSiblings(tree(), 'i2', 'i0') // move last item to front
    const list = next.children[0].children[0]
    expect(list.children.map((c) => c.id)).toEqual(['i2', 'i0', 'i1'])
    expect(list.children.map((c) => c.order)).toEqual([0, 1, 2])
  })

  it('is a no-op across containers (section id vs list-item id)', () => {
    const t = tree()
    expect(reorderSiblings(t, 'b', 'i0')).toBe(t)
  })

  it('is a no-op for unknown ids and for active === over', () => {
    const t = tree()
    expect(reorderSiblings(t, 'nope', 'a')).toBe(t)
    expect(reorderSiblings(t, 'a', 'a')).toBe(t)
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd react-dashboard && npm run test -- treeOps`
Expected: FAIL — `cloneWithFreshIds`, `addSection`, `reorderSiblings` not exported.

- [ ] **Step 3: Write the implementation**

In `react-dashboard/src/components/widgets/profile-tree/treeOps.js`:

(a) Export the existing clone helper — change its declaration from
`function cloneWithFreshIds(node) {` to:

```js
export function cloneWithFreshIds(node) {
```

(b) Replace the existing `addCustomSection` (the whole function) with:

```js
// Append a prebuilt section subtree to the root and renumber root children.
export function addSection(tree, sectionSubtree) {
  return { ...tree, children: renumber([...tree.children, sectionSubtree]) }
}

// Append a custom (role:null) section holding exactly one empty group (the
// section "exactly one child" invariant). Delegates to addSection.
export function addCustomSection(tree, name) {
  const section = {
    type: 'section', id: newId(), name: name || 'Section', role: null,
    order: 0, visible: true,
    children: [{
      type: 'group', id: newId(), name: name || 'Section', order: 0,
      visible: true, regen_lock: false, children: [],
    }],
  }
  return addSection(tree, section)
}

// Move the child `activeId` to `overId`'s index within the SAME sibling array
// and renumber. No-op when the ids live in different containers, either id is
// absent, or activeId === overId. Recurses through `children` only.
export function reorderSiblings(node, activeId, overId) {
  if (activeId === overId) return node
  if (!Array.isArray(node.children)) return node
  const ai = node.children.findIndex((c) => c.id === activeId)
  const oi = node.children.findIndex((c) => c.id === overId)
  if (ai !== -1 && oi !== -1) {
    const arr = node.children.slice()
    const [moved] = arr.splice(ai, 1)
    arr.splice(oi, 0, moved)
    return { ...node, children: renumber(arr) }
  }
  if (ai !== -1 || oi !== -1) return node // split across containers: no-op
  let changed = false
  const nc = node.children.map((c) => {
    const r = reorderSiblings(c, activeId, overId)
    if (r !== c) changed = true
    return r
  })
  return changed ? { ...node, children: nc } : node
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd react-dashboard && npm run test -- treeOps`
Expected: PASS (all existing + new describes).

- [ ] **Step 5: Commit**

```bash
git add react-dashboard/src/components/widgets/profile-tree/treeOps.js react-dashboard/src/components/widgets/profile-tree/treeOps.test.js
git commit -m "[feat] Add addSection + reorderSiblings tree helpers; export cloneWithFreshIds"
```

---

### Task 2: Recommended-section catalog (`sectionCatalog.js`)

**Files:**
- Create: `react-dashboard/src/components/widgets/profile-tree/sectionCatalog.js`
- Create: `react-dashboard/src/components/widgets/profile-tree/sectionCatalog.test.js`

**Interfaces:**
- Consumes: `newId`, `makeField`, `cloneWithFreshIds` from `treeOps` (Task 1).
- Produces:
  - `SECTION_TEMPLATES: Array<{ id, label, description, kind: 'list'|'taglist'|'blank', fields? }>` — the 7 + Blank.
  - `buildSectionFromTemplate(template) -> SectionNode` — a fresh `role:null` section subtree per the template (fresh ids throughout; list templates seeded with one empty item; taglist a single `[]` field; blank one empty group).

- [ ] **Step 1: Write the failing test**

Create `react-dashboard/src/components/widgets/profile-tree/sectionCatalog.test.js`:

```js
import { describe, it, expect } from 'vitest'
import { SECTION_TEMPLATES, buildSectionFromTemplate } from './sectionCatalog'

function allIds(node, acc = []) {
  acc.push(node.id)
  if (Array.isArray(node.children)) node.children.forEach((c) => allIds(c, acc))
  if (node.item_template) allIds(node.item_template, acc)
  return acc
}

const byId = (id) => SECTION_TEMPLATES.find((t) => t.id === id)

describe('SECTION_TEMPLATES', () => {
  it('contains the 7 recommended templates plus Blank', () => {
    expect(SECTION_TEMPLATES.map((t) => t.id)).toEqual([
      'certifications', 'awards', 'publications', 'volunteer',
      'languages', 'courses', 'interests', 'blank',
    ])
    SECTION_TEMPLATES.forEach((t) => {
      expect(typeof t.label).toBe('string')
      expect(typeof t.description).toBe('string')
    })
  })
})

describe('buildSectionFromTemplate', () => {
  it('builds a role:null section with all-fresh, unique ids', () => {
    const sec = buildSectionFromTemplate(byId('certifications'))
    expect(sec.type).toBe('section')
    expect(sec.role).toBeNull()
    expect(sec.name).toBe('Certifications')
    const ids = allIds(sec)
    expect(new Set(ids).size).toBe(ids.length) // all unique
  })

  it('list template: list child with matching item_template + one empty seeded item', () => {
    const sec = buildSectionFromTemplate(byId('certifications'))
    const list = sec.children[0]
    expect(list.type).toBe('list')
    expect(list.bullet_style).toBe('none')
    expect(list.item_template.children.map((f) => f.key)).toEqual(['name', 'issuer', 'date'])
    expect(list.item_template.children.map((f) => f.kind)).toEqual(['text', 'text', 'text'])
    expect(list.children).toHaveLength(1)
    const item = list.children[0]
    expect(item.id).not.toBe(list.item_template.id)
    expect(item.children.map((f) => f.key)).toEqual(['name', 'issuer', 'date'])
    expect(item.children.every((f) => f.value === '')).toBe(true)
  })

  it('volunteer template: Description field is markdown', () => {
    const sec = buildSectionFromTemplate(byId('volunteer'))
    const tmpl = sec.children[0].item_template
    expect(tmpl.children.map((f) => f.key)).toEqual(['organization', 'role', 'dates', 'description'])
    expect(tmpl.children[3].kind).toBe('markdown')
  })

  it('taglist template: single taglist field with empty array value', () => {
    const sec = buildSectionFromTemplate(byId('languages'))
    expect(sec.children).toHaveLength(1)
    const field = sec.children[0]
    expect(field.type).toBe('field')
    expect(field.kind).toBe('taglist')
    expect(field.value).toEqual([])
  })

  it('blank template: one empty group (section single-child invariant)', () => {
    const sec = buildSectionFromTemplate(byId('blank'))
    expect(sec.children).toHaveLength(1)
    expect(sec.children[0].type).toBe('group')
    expect(sec.children[0].children).toHaveLength(0)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd react-dashboard && npm run test -- sectionCatalog`
Expected: FAIL — `./sectionCatalog` not found.

- [ ] **Step 3: Write the implementation**

Create `react-dashboard/src/components/widgets/profile-tree/sectionCatalog.js`:

```js
// Static catalog of recommended profile sections. Each template builds a fully
// editable role:null custom section. Pure data + builders; no React, no I/O.
import { newId, makeField, cloneWithFreshIds } from './treeOps'

export const SECTION_TEMPLATES = [
  { id: 'certifications', label: 'Certifications', description: 'Name, issuer, date', kind: 'list',
    fields: [{ name: 'Name', kind: 'text' }, { name: 'Issuer', kind: 'text' }, { name: 'Date', kind: 'text' }] },
  { id: 'awards', label: 'Awards & Honors', description: 'Title, issuer, year', kind: 'list',
    fields: [{ name: 'Title', kind: 'text' }, { name: 'Issuer', kind: 'text' }, { name: 'Year', kind: 'text' }] },
  { id: 'publications', label: 'Publications', description: 'Title, venue, year, URL', kind: 'list',
    fields: [{ name: 'Title', kind: 'text' }, { name: 'Venue', kind: 'text' }, { name: 'Year', kind: 'text' }, { name: 'URL', kind: 'text' }] },
  { id: 'volunteer', label: 'Volunteer Experience', description: 'Org, role, dates, description', kind: 'list',
    fields: [{ name: 'Organization', kind: 'text' }, { name: 'Role', kind: 'text' }, { name: 'Dates', kind: 'text' }, { name: 'Description', kind: 'markdown' }] },
  { id: 'languages', label: 'Languages', description: 'Tag list of languages', kind: 'taglist' },
  { id: 'courses', label: 'Courses', description: 'Tag list of courses', kind: 'taglist' },
  { id: 'interests', label: 'Interests', description: 'Tag list of interests', kind: 'taglist' },
  { id: 'blank', label: 'Blank section', description: 'Empty custom section', kind: 'blank' },
]

const section = (label, child) => ({
  type: 'section', id: newId(), name: label, role: null, order: 0, visible: true,
  children: [child],
})

export function buildSectionFromTemplate(template) {
  if (template.kind === 'taglist') {
    const field = { ...makeField({ name: template.label, kind: 'taglist' }), order: 0 }
    return section(template.label, field)
  }
  if (template.kind === 'blank') {
    const group = {
      type: 'group', id: newId(), name: template.label, order: 0, visible: true,
      regen_lock: false, children: [],
    }
    return section(template.label, group)
  }
  // list template
  const itemTemplate = {
    type: 'group', id: newId(), name: 'Item', order: 0, visible: true, regen_lock: false,
    children: template.fields.map((f, i) => ({ ...makeField(f), order: i })),
  }
  const list = {
    type: 'list', id: newId(), name: template.label, order: 0, visible: true,
    bullet_style: 'none', item_template: itemTemplate,
    children: [cloneWithFreshIds(itemTemplate)],
  }
  return section(template.label, list)
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd react-dashboard && npm run test -- sectionCatalog`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add react-dashboard/src/components/widgets/profile-tree/sectionCatalog.js react-dashboard/src/components/widgets/profile-tree/sectionCatalog.test.js
git commit -m "[feat] Add recommended-section catalog + template builder"
```

---

### Task 3: `SectionGallery` component

**Files:**
- Create: `react-dashboard/src/components/widgets/profile-tree/SectionGallery.jsx`
- Create: `react-dashboard/src/components/widgets/profile-tree/SectionGallery.test.jsx`

**Interfaces:**
- Consumes: nothing (dumb/callback-driven).
- Produces: `SectionGallery({ templates, onAdd })` — a collapsed "+ Add section" button that expands into a card grid (one per template). Clicking a card calls `onAdd(template)` and collapses the panel.

- [ ] **Step 1: Write the failing test**

Create `react-dashboard/src/components/widgets/profile-tree/SectionGallery.test.jsx`:

```jsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { SectionGallery } from './SectionGallery'

const templates = [
  { id: 'certifications', label: 'Certifications', description: 'Name, issuer, date' },
  { id: 'blank', label: 'Blank section', description: 'Empty custom section' },
]

describe('SectionGallery', () => {
  it('toggles the panel and renders a card per template', () => {
    render(<SectionGallery templates={templates} onAdd={vi.fn()} />)
    // collapsed: only the add button
    expect(screen.queryByText('Certifications')).toBeNull()
    fireEvent.click(screen.getByText('+ Add section'))
    expect(screen.getByText('Certifications')).toBeInTheDocument()
    expect(screen.getByText('Blank section')).toBeInTheDocument()
  })

  it('calls onAdd with the chosen template and collapses', () => {
    const onAdd = vi.fn()
    render(<SectionGallery templates={templates} onAdd={onAdd} />)
    fireEvent.click(screen.getByText('+ Add section'))
    fireEvent.click(screen.getByText('Certifications'))
    expect(onAdd).toHaveBeenCalledWith(templates[0])
    // collapsed again
    expect(screen.queryByText('Blank section')).toBeNull()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd react-dashboard && npm run test -- SectionGallery`
Expected: FAIL — `./SectionGallery` not found.

- [ ] **Step 3: Write the implementation**

Create `react-dashboard/src/components/widgets/profile-tree/SectionGallery.jsx`:

```jsx
import { useState } from 'react'

// Card picker that replaces the plain "+ Add section" button. Dumb/callback-
// driven: clicking a card calls onAdd(template) and collapses the panel.
export function SectionGallery({ templates, onAdd }) {
  const [open, setOpen] = useState(false)

  if (!open) {
    return (
      <button
        type="button"
        className="self-start text-xs text-purple-400 hover:text-purple-300 mt-1"
        onClick={() => setOpen(true)}
      >+ Add section</button>
    )
  }

  return (
    <div className="flex flex-col gap-2 mt-1">
      <div className="flex items-center justify-between">
        <span className="text-xs text-space-dim">Add a section</span>
        <button
          type="button" aria-label="Close section gallery"
          className="text-space-dim hover:text-space-text text-sm leading-none"
          onClick={() => setOpen(false)}
        >×</button>
      </div>
      <div className="grid grid-cols-2 gap-2">
        {templates.map((t) => (
          <button
            key={t.id} type="button"
            className="text-left border border-space-border rounded-lg p-2 hover:border-purple-400 transition-colors"
            onClick={() => { onAdd(t); setOpen(false) }}
          >
            <div className="text-sm text-space-text">{t.label}</div>
            <div className="text-xs text-space-dim">{t.description}</div>
          </button>
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd react-dashboard && npm run test -- SectionGallery`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add react-dashboard/src/components/widgets/profile-tree/SectionGallery.jsx react-dashboard/src/components/widgets/profile-tree/SectionGallery.test.jsx
git commit -m "[feat] Add SectionGallery card picker"
```

---

### Task 4: Wire gallery + `reorder` op into `ProfileTreeEditor` (no DnD yet)

**Files:**
- Modify: `react-dashboard/src/components/widgets/profile-tree/ProfileTreeEditor.jsx`
- Modify: `react-dashboard/src/components/widgets/profile-tree/ProfileTreeEditor.test.jsx`

**Interfaces:**
- Consumes: `reorderSiblings`, `addSection` (Task 1); `SECTION_TEMPLATES`, `buildSectionFromTemplate` (Task 2); `SectionGallery` (Task 3).
- Produces: editor now adds sections from the gallery and exposes `ops.reorder(activeId, overId)` (consumed by DnD in Tasks 5–6).

- [ ] **Step 1: Update the failing test**

In `react-dashboard/src/components/widgets/profile-tree/ProfileTreeEditor.test.jsx`, REPLACE the existing `adds a custom section` test with these two tests:

```jsx
  it('adds a blank custom section from the gallery', async () => {
    render(<ProfileTreeEditor profileId={1} />)
    await screen.findByText('Skills')
    fireEvent.click(screen.getByText('+ Add section'))
    fireEvent.click(screen.getByText('Blank section'))
    expect(await screen.findByText('Blank section')).toBeInTheDocument()
  })

  it('adds a recommended template section from the gallery', async () => {
    render(<ProfileTreeEditor profileId={1} />)
    await screen.findByText('Skills')
    fireEvent.click(screen.getByText('+ Add section'))
    fireEvent.click(screen.getByText('Certifications'))
    expect(await screen.findByText('Certifications')).toBeInTheDocument()
  })
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd react-dashboard && npm run test -- ProfileTreeEditor`
Expected: FAIL — clicking `+ Add section` no longer yields `New section`; `Blank section`/`Certifications` cards don't exist yet.

- [ ] **Step 3: Write the implementation**

In `react-dashboard/src/components/widgets/profile-tree/ProfileTreeEditor.jsx`:

(a) Update the imports near the top — replace the `treeOps` import and add the new modules:

```jsx
import {
  updateNode, removeNode, moveNode, addField, addListItem, addSection, reorderSiblings,
} from './treeOps'
import { SectionGallery } from './SectionGallery'
import { SECTION_TEMPLATES, buildSectionFromTemplate } from './sectionCatalog'
```

(b) Add a `reorder` entry to the `ops` bundle (alongside the existing `addField` line):

```jsx
    reorder: useCallback((activeId, overId) => setTree((t) => reorderSiblings(t, activeId, overId)), []),
```

(c) Replace the inline `+ Add section` button (the `<button … onClick={() => setTree((t) => addCustomSection(t, 'New section'))}>+ Add section</button>`) with:

```jsx
      <SectionGallery
        templates={SECTION_TEMPLATES}
        onAdd={(tpl) => setTree((t) => addSection(t, buildSectionFromTemplate(tpl)))}
      />
```

Note: `addCustomSection` is no longer imported here (the gallery's Blank template covers it); leave `addCustomSection` in `treeOps.js` for its unit tests.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd react-dashboard && npm run test -- ProfileTreeEditor`
Expected: PASS (all ProfileTreeEditor tests, including the two new gallery tests).

- [ ] **Step 5: Commit**

```bash
git add react-dashboard/src/components/widgets/profile-tree/ProfileTreeEditor.jsx react-dashboard/src/components/widgets/profile-tree/ProfileTreeEditor.test.jsx
git commit -m "[feat] Wire section gallery and reorder op into ProfileTreeEditor"
```

---

### Task 5: Section drag-drop (dnd-kit) in `ProfileTreeEditor`

**Files:**
- Modify: `react-dashboard/package.json`
- Modify: `react-dashboard/src/components/widgets/profile-tree/TreeNode.jsx`
- Modify: `react-dashboard/src/components/widgets/profile-tree/ProfileTreeEditor.jsx`
- Modify: `react-dashboard/src/components/widgets/profile-tree/ProfileTreeEditor.test.jsx`

**Interfaces:**
- Consumes: `ops.reorder` (Task 4); `SectionView` (Task 6 of 2B).
- Produces: `SectionView` gains an optional `dragHandle` prop; sections are wrapped in a `DndContext`/`SortableContext`; a `Drag to reorder section` handle is rendered per section.

- [ ] **Step 1: Install dnd-kit**

Run (from `react-dashboard/`):

```bash
npm install @dnd-kit/core@^6 @dnd-kit/sortable@^9 @dnd-kit/utilities@^3
```

Expected: deps added to `package.json` `dependencies`, no errors.

- [ ] **Step 2: Write the failing test**

In `react-dashboard/src/components/widgets/profile-tree/ProfileTreeEditor.test.jsx`, add this test inside the `describe('ProfileTreeEditor', …)` block:

```jsx
  it('renders a drag handle for each section', async () => {
    render(<ProfileTreeEditor profileId={1} />)
    await screen.findByText('Skills')
    expect(screen.getAllByLabelText('Drag to reorder section')).toHaveLength(1)
  })
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd react-dashboard && npm run test -- ProfileTreeEditor`
Expected: FAIL — no `Drag to reorder section` handle yet.

- [ ] **Step 4: Add the `dragHandle` prop to `SectionView`**

In `react-dashboard/src/components/widgets/profile-tree/TreeNode.jsx`, change the `SectionView` signature and render the handle next to the collapse caret.

Change the function signature line:

```jsx
export function SectionView({ section, isFirst, isLast, ops, dragHandle }) {
```

In the header's left `<span>` (the one containing the collapse button and `RenameLabel`), insert `{dragHandle}` as the first child:

```jsx
        <span className="inline-flex items-center gap-2">
          {dragHandle}
          <button
            type="button"
            aria-label={collapsed ? 'Expand section' : 'Collapse section'}
            className="px-1 text-space-dim hover:text-space-text transition-colors"
            onClick={() => setCollapsed((c) => !c)}
          >{collapsed ? '▸' : '▾'}</button>
          <RenameLabel
            name={section.name} editable
            onRename={(n) => ops.rename(section.id, n)}
          />
        </span>
```

- [ ] **Step 5: Wrap sections in a DndContext in `ProfileTreeEditor`**

In `react-dashboard/src/components/widgets/profile-tree/ProfileTreeEditor.jsx`:

(a) Add imports near the top:

```jsx
import {
  DndContext, closestCenter, PointerSensor, KeyboardSensor, useSensor, useSensors,
} from '@dnd-kit/core'
import {
  SortableContext, verticalListSortingStrategy, useSortable, sortableKeyboardCoordinates,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
```

(b) Add this `SortableSection` wrapper component at the bottom of the file (after the default export):

```jsx
function SortableSection({ section, isFirst, isLast, ops }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: section.id })
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  }
  const handle = (
    <button
      type="button" aria-label="Drag to reorder section"
      className="cursor-grab active:cursor-grabbing px-1 text-space-dim hover:text-space-text"
      {...attributes} {...listeners}
    >⋮⋮</button>
  )
  return (
    <div ref={setNodeRef} style={style}>
      <SectionView
        section={section} isFirst={isFirst} isLast={isLast} ops={ops} dragHandle={handle}
      />
    </div>
  )
}
```

(c) Inside `ProfileTreeEditor`, add the sensors hook alongside the other hooks (BEFORE the `if (loading) …` early returns, e.g. right after the `ops` bundle):

```jsx
  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )
  const handleDragEnd = ({ active, over }) => {
    if (over && active.id !== over.id) ops.reorder(active.id, over.id)
  }
```

(d) Replace the `sections.map(…)` render block with a DndContext-wrapped sortable list:

```jsx
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={sections.map((s) => s.id)} strategy={verticalListSortingStrategy}>
          {sections.map((section, i) => (
            <SortableSection
              key={section.id} section={section}
              isFirst={i === 0} isLast={i === sections.length - 1} ops={ops}
            />
          ))}
        </SortableContext>
      </DndContext>
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd react-dashboard && npm run test -- ProfileTreeEditor TreeNode`
Expected: PASS — the drag-handle test passes; existing ProfileTreeEditor and TreeNode tests still pass (`SectionView` without a `dragHandle` is unchanged).

- [ ] **Step 7: Commit**

```bash
git add react-dashboard/package.json react-dashboard/package-lock.json react-dashboard/src/components/widgets/profile-tree/TreeNode.jsx react-dashboard/src/components/widgets/profile-tree/ProfileTreeEditor.jsx react-dashboard/src/components/widgets/profile-tree/ProfileTreeEditor.test.jsx
git commit -m "[feat] Add dnd-kit section drag-drop with a11y fallback retained"
```

---

### Task 6: List-item drag-drop in `ListView` + docs

**Files:**
- Modify: `react-dashboard/src/components/widgets/profile-tree/TreeNode.jsx`
- Modify: `react-dashboard/src/components/widgets/profile-tree/TreeNode.test.jsx`
- Modify: `react-dashboard/CONTEXT.md`, `core/CONTEXT.md`

**Interfaces:**
- Consumes: `ops.reorder` (Task 4); dnd-kit (Task 5).
- Produces: list entries are drag-reorderable within their list; `Drag to reorder item` handle per entry. `↑`/`↓` buttons retained.

- [ ] **Step 1: Write the failing test**

In `react-dashboard/src/components/widgets/profile-tree/TreeNode.test.jsx`, add this test to the `describe('SectionView preset', …)` block:

```jsx
  it('renders a drag handle per list entry', () => {
    render(<SectionView section={presetListSection} isFirst={false} isLast ops={noopOps()} />)
    fireEvent.click(screen.getByLabelText('Expand section')) // collapsed by default
    expect(screen.getAllByLabelText('Drag to reorder item')).toHaveLength(1)
  })
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd react-dashboard && npm run test -- TreeNode`
Expected: FAIL — no `Drag to reorder item` handle yet.

- [ ] **Step 3: Add dnd-kit imports to `TreeNode.jsx`**

At the top of `react-dashboard/src/components/widgets/profile-tree/TreeNode.jsx`, add:

```jsx
import {
  DndContext, closestCenter, PointerSensor, KeyboardSensor, useSensor, useSensors,
} from '@dnd-kit/core'
import {
  SortableContext, verticalListSortingStrategy, useSortable, sortableKeyboardCoordinates,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
```

- [ ] **Step 4: Replace `ListView` with a sortable version**

In `react-dashboard/src/components/widgets/profile-tree/TreeNode.jsx`, replace the entire existing `ListView` function with a `SortableEntry` wrapper + a DnD-wrapped `ListView`:

```jsx
// One list entry, made sortable. Keeps the ↑/↓ buttons as the a11y fallback.
function SortableEntry({ item, index, count, ops }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: item.id })
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  }
  return (
    <div
      ref={setNodeRef} style={style}
      className="border border-space-border/50 rounded-lg p-3 flex flex-col gap-2"
    >
      <div className={headerRow}>
        <span className="inline-flex items-center gap-2">
          <button
            type="button" aria-label="Drag to reorder item"
            className="cursor-grab active:cursor-grabbing px-1 text-space-dim hover:text-space-text"
            {...attributes} {...listeners}
          >⋮⋮</button>
          <span className="text-xs text-space-dim">Entry {index + 1}</span>
        </span>
        <span className="inline-flex items-center">
          <MoveButtons
            canUp={index > 0} canDown={index < count - 1}
            onUp={() => ops.move(item.id, -1)} onDown={() => ops.move(item.id, 1)}
          />
          <RemoveButton onRemove={() => ops.remove(item.id)} label="Remove item" />
        </span>
      </div>
      <GroupView group={item} fieldsEditable={false} ops={ops} />
    </div>
  )
}

// A repeating list: each item is a fixed-shape group (no field add/remove);
// items can be added (clone template), removed, reordered (drag or ↑/↓).
function ListView({ list, ops }) {
  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )
  const handleDragEnd = ({ active, over }) => {
    if (over && active.id !== over.id) ops.reorder(active.id, over.id)
  }
  return (
    <div className="flex flex-col gap-4">
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={list.children.map((i) => i.id)} strategy={verticalListSortingStrategy}>
          {list.children.map((item, i) => (
            <SortableEntry
              key={item.id} item={item} index={i} count={list.children.length} ops={ops}
            />
          ))}
        </SortableContext>
      </DndContext>
      <AddButton label="+ Add entry" onClick={() => ops.addItem(list.id)} />
    </div>
  )
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd react-dashboard && npm run test -- TreeNode`
Expected: PASS — the new drag-handle test passes; existing list tests (add entry, remove item, edit value) still pass.

- [ ] **Step 6: Run the full suite + build**

Run (from `react-dashboard/`): `npm run test`
Expected: PASS (all suites: treeOps, sectionCatalog, SectionGallery, fieldWidgets, structuralControls, TreeNode, ProfileTreeEditor, api, smoke).

Run: `npm run build`
Expected: build succeeds.

- [ ] **Step 7: Update docs**

In `react-dashboard/CONTEXT.md` (profile-tree rows): note that 2C adds drag-drop reorder of sections + list items via `dnd-kit` (with the `↑`/`↓` buttons retained as the a11y fallback) and a recommended-section gallery (`SectionGallery.jsx` + `sectionCatalog.js`, 7 templates + Blank) replacing the old "+ Add section" button. Drag-drop is wired around the presentational components: `SectionView` takes an optional `dragHandle`; `ProfileTreeEditor` owns the section-level `DndContext`; `ListView` owns a per-list `DndContext`.

In `core/CONTEXT.md` → "Profile Schema Engine": add a line that sub-project **2C** ships the graphical builder (drag-drop section/item reorder + recommended-section gallery) on the 2B editor; still no document rendering of custom sections (that is #4).

- [ ] **Step 8: Commit**

```bash
git add react-dashboard/src/components/widgets/profile-tree/TreeNode.jsx react-dashboard/src/components/widgets/profile-tree/TreeNode.test.jsx react-dashboard/CONTEXT.md core/CONTEXT.md
git commit -m "[feat] Add list-item drag-drop; document 2C builder"
```

---

## Self-Review

**Spec coverage:**
- Drag-drop sections → Task 5. ✓
- Drag-drop list items → Task 6. ✓
- `↑`/`↓` retained as fallback → Tasks 5 (sections keep them) & 6 (items keep `MoveButtons`). ✓
- dnd-kit dependency → Task 5 Step 1. ✓
- Recommended-section catalog (7 + Blank), list templates seed one empty item, taglist single empty field → Task 2. ✓
- `SectionGallery` replaces "+ Add section" → Tasks 3 (component) + 4 (wiring). ✓
- `reorderSiblings`/`addSection`, export `cloneWithFreshIds` → Task 1. ✓
- DnD wired around presentational components (optional `dragHandle`, per-container `DndContext`) so 2B unit tests stay valid → Tasks 5/6. ✓
- No backend/API changes; persistence via existing PUT → no task touches the server. ✓
- Docs updated → Task 6 Step 7. ✓
- Out of scope (field-level DnD, cross-section moves, document rendering) → not implemented. ✓

**Placeholder scan:** none — every code step contains complete code; every run step has an exact command + expected result.

**Type/identifier consistency:** `ops.reorder(activeId, overId)` defined in Task 4 and called by `handleDragEnd` in Tasks 5/6. `reorderSiblings(tree, activeId, overId)` / `addSection(tree, section)` / `cloneWithFreshIds(node)` signatures match between Task 1 (definition) and Tasks 2/4 (use). `SECTION_TEMPLATES` / `buildSectionFromTemplate(template)` match between Task 2 and Tasks 3-test/4. `SectionGallery({ templates, onAdd })` matches between Task 3 and Task 4. `SectionView`'s new `dragHandle` prop is optional, so 2B call sites and unit tests remain valid; the new call site (`SortableSection`, Task 5) supplies it. dnd-kit hook names (`useSortable`, `SortableContext`, `DndContext`, `CSS.Transform.toString`) are consistent across Tasks 5/6.
