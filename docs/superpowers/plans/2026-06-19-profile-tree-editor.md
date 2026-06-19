# Profile Tree Editor (2B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hardcoded doc-section accordions in the React profile editor with a generic, tree-driven editor that reads/writes the whole profile tree via the 2A `GET`/`PUT /api/config/profiles/{id}/tree` endpoints, preserving node IDs and tree-only data.

**Architecture:** A new `react-dashboard/src/components/widgets/profile-tree/` module. Pure tree-mutation helpers (`treeOps.js`) hold all structural logic (immutable update/add/remove/move with `order` renormalization + provenance rules) and are fully unit-tested without rendering. Presentational components (`fieldWidgets`, `structuralControls`, `TreeNode`) are dumb and callback-driven. `ProfileTreeEditor` owns I/O, state, dirty tracking, and the whole-tree Save (with 422 handling). The editor is dropped into `ProfileDetail.jsx` in place of the six doc-section accordions; name/preferences/Prompts and the flat `update_profile` endpoint are untouched. This is also the project's first frontend test suite (Vitest + React Testing Library).

**Tech Stack:** React 18, Vite 5, Vitest, React Testing Library, jsdom, Tailwind.

## Roadmap Context (read first — this plan starts a fresh session)

This is **sub-project 2B** of the "user-defined resume sections" initiative
(replace the hardcoded 5-section résumé model with a user-definable schema
tree). Full roadmap lives in the auto-memory `project-profile-schema-engine`
and `core/CONTEXT.md` → "Profile Schema Engine". Sequence:

1. **Schema engine** — DONE, merged to local `main`. Recursive tree
   (`root → section → list/group → field`) is the profile source of truth in
   `core/profile_tree.py`.
2. **Builder UI** — phased:
   - **2A** (write-path consolidation + tree API) — DONE, merged to local
     `main`. Added `apply_flat_to_tree`, `merge_flat_into_stored`, and
     `GET`/`PUT /api/config/profiles/{id}/tree`.
   - **2B** (this plan) — tree-driven profile editor on those endpoints.
   - **2C** (next, after 2B) — graphical drag-drop custom-section builder +
     recommended-section gallery. 2B deliberately uses up/down reorder and
     plain add-forms; drag-drop is 2C's job.
3. **Schema-driven LLM generation** against custom sections.
4. **Schema-driven rendering** of custom sections on documents (until this
   ships, custom sections are storable/editable but do NOT appear on generated
   résumés/cover letters — call this out in the 2B UI if natural, else leave).
5. **Onboarding parse** that maps novel sections.

**RELEASE CONSTRAINT:** do NOT push `main` until the entire swap (through #5)
is complete. Each sub-project merges to LOCAL `main` only.

**Before starting 2B:** create a feature branch off `main`
(`git checkout -b feat/profile-tree-editor`). On completion, use
`superpowers:finishing-a-development-branch` → merge to local `main` (no push).

**After 2B:** brainstorm → spec → plan → impl **2C**, then sub-projects #3, #4,
#5 in order. Update the `project-profile-schema-engine` memory when 2B lands.

## Global Constraints

- The profile **tree** is the source of truth (2A). The editor persists only via `PUT /api/config/profiles/{id}/tree`; it never writes doc-section data through the flat `update_profile` endpoint.
- Server tree invariants the client MUST respect (else the PUT 422s):
  - Every node `id` is unique across the whole tree.
  - A `GroupNode`'s child field `key`s are unique within that group.
  - A `SectionNode` has **exactly one** child (one group **or** one list **or** one field).
  - A `ListNode`'s items must each match the `item_template`'s `(key, kind)` shape — so new items are cloned from `item_template`; you may NOT add/remove fields on individual list items.
  - Among a `RootNode`/`SectionNode`/`ListNode`'s children, `order` values are unique. The client renormalizes affected siblings to `0..n-1` after every add/remove/move.
  - Caps: ≤ 500 nodes, ≤ 6 levels deep.
- Field `value` Python/JSON types by `kind`: `text`/`markdown` → string; `bullets`/`taglist` → array of strings.
- **Preset sections** (`role ∈ {header, summary, experience, education, projects, skills}`): name is renamable (cosmetic), `visible` toggleable, reorderable; **not** removable (hide via `visible` instead); their group fields' values are editable but fields cannot be added/removed/renamed (keys are contractually mapped by `tree_to_legacy`). Preset **list** sections allow add/remove/reorder of **items**.
- **Custom sections** (`role === null`): full control — rename, visible, reorder, remove, add/remove/rename fields, choose field kind on add.
- New nodes (custom section/field/list item) are created client-side with a fresh id via `crypto.randomUUID()`; on a successful PUT the editor replaces its state with the server's returned canonical tree.
- Attributes NOT edited in 2B (`llm_output`, `llm_input`, `llm_instructions`, `regen_lock`, `bullet_style`, `min`, `max`) must round-trip untouched — never drop or overwrite them when cloning/updating.
- JS style: match the existing dashboard (ES modules, function components, hooks, Tailwind utility classes, the shared `inputClass` look). Commit format `[type] Imperative subject`; types `feat|fix|refactor|docs|test|chore`. No Claude/Anthropic attribution, no `Co-Authored-By`.
- Frontend tests run with `npm run test` (added in Task 1) from `react-dashboard/`. Each task: write failing test → run → implement → run green → commit.

## File Structure

- **Create** `react-dashboard/vitest.config.js` — Vitest config (jsdom env, setup file).
- **Create** `react-dashboard/src/test/setup.js` — RTL/jest-dom setup.
- **Modify** `react-dashboard/package.json` — dev deps + `test` scripts.
- **Modify** `react-dashboard/src/api.js` — add `getProfileTree`, `putProfileTree`.
- **Create** `react-dashboard/src/components/widgets/profile-tree/treeOps.js` — pure tree helpers + provenance rules.
- **Create** `.../profile-tree/treeOps.test.js`
- **Create** `.../profile-tree/fieldWidgets.jsx` + `fieldWidgets.test.jsx`
- **Create** `.../profile-tree/structuralControls.jsx` + `structuralControls.test.jsx`
- **Create** `.../profile-tree/TreeNode.jsx` + `TreeNode.test.jsx`
- **Create** `.../profile-tree/ProfileTreeEditor.jsx` + `ProfileTreeEditor.test.jsx`
- **Modify** `react-dashboard/src/components/widgets/ProfileDetail.jsx` — swap the six doc-section accordions for `<ProfileTreeEditor>`, delete the now-dead section components/helpers.
- **Modify** `react-dashboard/CONTEXT.md` and `core/CONTEXT.md` — document 2B.

---

### Task 1: Frontend test harness (Vitest + RTL)

**Files:**
- Modify: `react-dashboard/package.json`
- Create: `react-dashboard/vitest.config.js`, `react-dashboard/src/test/setup.js`, `react-dashboard/src/test/smoke.test.js`

**Interfaces:**
- Consumes: nothing.
- Produces: a working `npm run test` command and a jsdom + jest-dom test environment that later tasks rely on.

- [ ] **Step 1: Install dev dependencies**

Run (from `react-dashboard/`):

```bash
npm install -D vitest@^2 @testing-library/react@^16 @testing-library/jest-dom@^6 @testing-library/user-event@^14 jsdom@^25
```

Expected: deps added to `package.json` `devDependencies`, no errors.

- [ ] **Step 2: Add test scripts to `package.json`**

In `react-dashboard/package.json`, add to the `"scripts"` object (alongside `dev`/`build`):

```json
    "test": "vitest run",
    "test:watch": "vitest"
```

- [ ] **Step 3: Create the Vitest config**

Create `react-dashboard/vitest.config.js`:

```js
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.js'],
    include: ['src/**/*.{test,spec}.{js,jsx}'],
  },
})
```

- [ ] **Step 4: Create the setup file**

Create `react-dashboard/src/test/setup.js`:

```js
import '@testing-library/jest-dom'
```

- [ ] **Step 5: Write a smoke test**

Create `react-dashboard/src/test/smoke.test.js`:

```js
import { describe, it, expect } from 'vitest'

describe('test harness', () => {
  it('runs and supports jsdom', () => {
    const el = document.createElement('div')
    el.textContent = 'ok'
    expect(el.textContent).toBe('ok')
  })
})
```

- [ ] **Step 6: Run the smoke test**

Run (from `react-dashboard/`): `npm run test`
Expected: PASS (1 test). Confirms Vitest + jsdom work.

- [ ] **Step 7: Commit**

```bash
git add react-dashboard/package.json react-dashboard/package-lock.json react-dashboard/vitest.config.js react-dashboard/src/test/setup.js react-dashboard/src/test/smoke.test.js
git commit -m "[test] Add Vitest + React Testing Library frontend harness"
```

---

### Task 2: API wrappers (`getProfileTree`, `putProfileTree`)

**Files:**
- Modify: `react-dashboard/src/api.js`
- Create: `react-dashboard/src/api.profileTree.test.js`

**Interfaces:**
- Consumes: the existing module-private `_fetch` in `api.js`.
- Produces:
  - `getProfileTree(id) -> Promise<{tree: object}>` — `GET /api/config/profiles/${id}/tree`.
  - `putProfileTree(id, tree) -> Promise<{tree: object}>` — `PUT /api/config/profiles/${id}/tree` with body `{ tree }`.

- [ ] **Step 1: Write the failing test**

Create `react-dashboard/src/api.profileTree.test.js`:

```js
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { getProfileTree, putProfileTree } from './api'

describe('profile tree api', () => {
  beforeEach(() => {
    global.fetch = vi.fn(async () => ({
      ok: true,
      status: 200,
      headers: { get: () => 'application/json' },
      json: async () => ({ tree: { type: 'root', id: 'r', children: [] } }),
    }))
  })
  afterEach(() => { vi.restoreAllMocks() })

  it('getProfileTree GETs the tree route', async () => {
    const out = await getProfileTree(7)
    expect(global.fetch).toHaveBeenCalledWith('/api/config/profiles/7/tree', undefined)
    expect(out.tree.type).toBe('root')
  })

  it('putProfileTree PUTs {tree} as JSON', async () => {
    const tree = { type: 'root', id: 'r', children: [] }
    await putProfileTree(7, tree)
    const [url, opts] = global.fetch.mock.calls[0]
    expect(url).toBe('/api/config/profiles/7/tree')
    expect(opts.method).toBe('PUT')
    expect(JSON.parse(opts.body)).toEqual({ tree })
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- api.profileTree`
Expected: FAIL — `getProfileTree`/`putProfileTree` are not exported.

- [ ] **Step 3: Add the wrappers**

In `react-dashboard/src/api.js`, after the existing `updateProfile` export, add:

```js
export const getProfileTree = (id) =>
  _fetch(`/api/config/profiles/${id}/tree`)

export const putProfileTree = (id, tree) =>
  _fetch(`/api/config/profiles/${id}/tree`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tree }),
  })
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test -- api.profileTree`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add react-dashboard/src/api.js react-dashboard/src/api.profileTree.test.js
git commit -m "[feat] Add profile tree GET/PUT api wrappers"
```

---

### Task 3: Pure tree helpers (`treeOps.js`)

**Files:**
- Create: `react-dashboard/src/components/widgets/profile-tree/treeOps.js`
- Create: `react-dashboard/src/components/widgets/profile-tree/treeOps.test.js`

**Interfaces:**
- Consumes: nothing (pure functions over plain tree objects matching the 2A node JSON).
- Produces (all are pure; trees are plain objects, never mutated in place):
  - `PRESET_ROLES: Set<string>`
  - `isPresetSection(section) -> boolean`
  - `newId() -> string`
  - `renumber(children) -> children` — returns array with each child's `order` set to its index.
  - `updateNode(tree, id, mutator) -> tree` — immutably replace the node whose `id === id` with `mutator(node)`; recurses through `children` and `item_template`.
  - `removeNode(tree, id) -> tree` — remove the child with `id` from its parent and renumber siblings.
  - `moveNode(tree, id, delta) -> tree` — swap the child with `id` by `delta` (±1) within its sibling list and renumber; no-op at the ends.
  - `makeField({name, kind}) -> FieldNode` — a fresh field with a unique-able key seed and kind-correct empty value.
  - `addField(tree, groupId, {name, kind}) -> tree` — append a new field to the group, with a key unique within that group, and renumber.
  - `addListItem(tree, listId) -> tree` — clone the list's `item_template` with fresh ids and append, renumber.
  - `addCustomSection(tree, name) -> tree` — append a custom (`role: null`) section containing exactly one empty group, renumber root children.

- [ ] **Step 1: Write the failing test**

Create `react-dashboard/src/components/widgets/profile-tree/treeOps.test.js`:

```js
import { describe, it, expect } from 'vitest'
import {
  PRESET_ROLES, isPresetSection, renumber, updateNode, removeNode,
  moveNode, makeField, addField, addListItem, addCustomSection,
} from './treeOps'

// Minimal tree: skills (preset, single field) + experience (preset list).
function sampleTree() {
  return {
    type: 'root', id: 'r', children: [
      {
        type: 'section', id: 'sec-skills', name: 'Skills', role: 'skills',
        order: 0, visible: true, children: [
          { type: 'field', id: 'f-skills', name: 'Skills', key: 'skills',
            order: 0, visible: true, kind: 'taglist', value: ['Python'],
            llm_output: false, llm_instructions: '', llm_input: false,
            regen_lock: false, min: null, max: null },
        ],
      },
      {
        type: 'section', id: 'sec-exp', name: 'Experience', role: 'experience',
        order: 1, visible: true, children: [
          {
            type: 'list', id: 'list-exp', name: 'Experience', order: 0,
            visible: true, bullet_style: 'none',
            item_template: {
              type: 'group', id: 'tmpl', name: 'Entry', order: 0, visible: true,
              regen_lock: false, children: [
                { type: 'field', id: 'tf-co', name: 'Company', key: 'company',
                  order: 0, visible: true, kind: 'text', value: '',
                  llm_output: false, llm_instructions: '', llm_input: false,
                  regen_lock: false, min: null, max: null },
              ],
            },
            children: [
              {
                type: 'group', id: 'item-0', name: 'Entry', order: 0,
                visible: true, regen_lock: false, children: [
                  { type: 'field', id: 'i0-co', name: 'Company', key: 'company',
                    order: 0, visible: true, kind: 'text', value: 'Acme',
                    llm_output: false, llm_instructions: '', llm_input: false,
                    regen_lock: false, min: null, max: null },
                ],
              },
            ],
          },
        ],
      },
    ],
  }
}

describe('provenance', () => {
  it('marks preset roles', () => {
    expect(PRESET_ROLES.has('experience')).toBe(true)
    expect(isPresetSection({ type: 'section', role: 'skills' })).toBe(true)
    expect(isPresetSection({ type: 'section', role: null })).toBe(false)
  })
})

describe('renumber', () => {
  it('sets order to index', () => {
    const out = renumber([{ order: 5 }, { order: 9 }, { order: 0 }])
    expect(out.map(c => c.order)).toEqual([0, 1, 2])
  })
})

describe('updateNode', () => {
  it('replaces a deep field immutably, preserving siblings and ids', () => {
    const tree = sampleTree()
    const next = updateNode(tree, 'i0-co', n => ({ ...n, value: 'NewCo' }))
    expect(next).not.toBe(tree)
    const item = next.children[1].children[0].children[0].children[0]
    expect(item.value).toBe('NewCo')
    expect(item.id).toBe('i0-co')
    // untouched branch keeps identity
    expect(next.children[0]).toBe(tree.children[0])
  })

  it('does not run mutator on item_template when targeting an item', () => {
    const tree = sampleTree()
    const next = updateNode(tree, 'i0-co', n => ({ ...n, value: 'X' }))
    const tmplField = next.children[1].children[0].children[0].item_template.children[0]
    expect(tmplField.value).toBe('')
  })
})

describe('removeNode', () => {
  it('removes a list item and renumbers siblings', () => {
    let tree = sampleTree()
    tree = addListItem(tree, 'list-exp') // now 2 items, orders 0,1
    const list = tree.children[1].children[0]
    const secondId = list.children[1].id
    tree = removeNode(tree, secondId)
    const after = tree.children[1].children[0]
    expect(after.children).toHaveLength(1)
    expect(after.children[0].id).toBe('item-0')
    expect(after.children.map(c => c.order)).toEqual([0])
  })
})

describe('moveNode', () => {
  it('swaps siblings and renumbers; no-op past the ends', () => {
    let tree = addCustomSection(sampleTree(), 'Awards') // appended at root index 2
    const awardsId = tree.children[2].id
    tree = moveNode(tree, awardsId, -1) // move up to index 1
    expect(tree.children[1].id).toBe(awardsId)
    expect(tree.children.map(c => c.order)).toEqual([0, 1, 2])
    const top = moveNode(tree, tree.children[0].id, -1) // already first
    expect(top.children[0].id).toBe(tree.children[0].id)
  })
})

describe('makeField + addField', () => {
  it('adds a kind-correct field with a unique key into a group', () => {
    let tree = addCustomSection(sampleTree(), 'Awards')
    const groupId = tree.children[2].children[0].id
    tree = addField(tree, groupId, { name: 'Award', kind: 'text' })
    tree = addField(tree, groupId, { name: 'Award', kind: 'bullets' })
    const group = tree.children[2].children[0]
    expect(group.children).toHaveLength(2)
    const keys = group.children.map(f => f.key)
    expect(new Set(keys).size).toBe(2) // unique despite same name
    expect(group.children[0].value).toBe('')      // text
    expect(group.children[1].value).toEqual([])    // bullets
    expect(group.children.map(f => f.order)).toEqual([0, 1])
  })
})

describe('addListItem', () => {
  it('clones item_template with fresh ids and empty values', () => {
    let tree = addListItem(sampleTree(), 'list-exp')
    const list = tree.children[1].children[0]
    expect(list.children).toHaveLength(2)
    const fresh = list.children[1]
    expect(fresh.id).not.toBe('item-0')
    expect(fresh.id).not.toBe('tmpl')
    expect(fresh.children[0].key).toBe('company')   // shape matches template
    expect(fresh.children[0].value).toBe('')
    expect(fresh.children[0].id).not.toBe('tf-co')  // fresh field id
    expect(list.children.map(c => c.order)).toEqual([0, 1])
  })
})

describe('addCustomSection', () => {
  it('appends a role:null section with exactly one empty group', () => {
    const tree = addCustomSection(sampleTree(), 'Awards')
    expect(tree.children).toHaveLength(3)
    const sec = tree.children[2]
    expect(sec.role).toBeNull()
    expect(sec.name).toBe('Awards')
    expect(sec.children).toHaveLength(1)            // section invariant
    expect(sec.children[0].type).toBe('group')
    expect(sec.children[0].children).toHaveLength(0)
    expect(tree.children.map(c => c.order)).toEqual([0, 1, 2])
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- treeOps`
Expected: FAIL — module `./treeOps` not found / exports undefined.

- [ ] **Step 3: Write the implementation**

Create `react-dashboard/src/components/widgets/profile-tree/treeOps.js`:

```js
// Pure, immutable helpers over the profile tree (plain objects matching the
// server's node JSON). No React, no I/O. All functions return new trees; they
// never mutate their inputs.

export const PRESET_ROLES = new Set([
  'header', 'summary', 'experience', 'education', 'projects', 'skills',
])

export const isPresetSection = (section) =>
  section?.type === 'section' && PRESET_ROLES.has(section.role)

export const newId = () => crypto.randomUUID()

// Return a copy of `children` with each element's `order` set to its index.
// Preserves object identity for elements already correctly numbered.
export const renumber = (children) =>
  children.map((c, i) => (c.order === i ? c : { ...c, order: i }))

const slugify = (s) =>
  String(s || '').toLowerCase().trim().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '')

function uniqueKey(base, existing) {
  const seed = base || 'field'
  let k = seed
  let n = 2
  while (existing.includes(k)) {
    k = `${seed}_${n}`
    n += 1
  }
  return k
}

// Immutably replace the node whose id === id with mutator(node). Recurses
// through `children` arrays and a list's `item_template`. Branches that do not
// contain the target keep their object identity (cheap, render-friendly).
export function updateNode(node, id, mutator) {
  if (node.id === id) return mutator(node)
  let next = node
  if (Array.isArray(node.children)) {
    const nc = node.children.map((c) => updateNode(c, id, mutator))
    if (nc.some((c, i) => c !== node.children[i])) {
      next = { ...next, children: nc }
    }
  }
  if (node.item_template) {
    const nt = updateNode(node.item_template, id, mutator)
    if (nt !== node.item_template) {
      next = { ...next, item_template: nt }
    }
  }
  return next
}

// Remove the child with `id` from whichever parent holds it; renumber that
// parent's surviving children. Recurses through children only (never templates).
export function removeNode(node, id) {
  if (!Array.isArray(node.children)) return node
  if (node.children.some((c) => c.id === id)) {
    return { ...node, children: renumber(node.children.filter((c) => c.id !== id)) }
  }
  let changed = false
  const nc = node.children.map((c) => {
    const r = removeNode(c, id)
    if (r !== c) changed = true
    return r
  })
  return changed ? { ...node, children: nc } : node
}

// Swap the child with `id` by `delta` (±1) within its sibling array and
// renumber. No-op at the ends or if not found.
export function moveNode(node, id, delta) {
  if (!Array.isArray(node.children)) return node
  const idx = node.children.findIndex((c) => c.id === id)
  if (idx !== -1) {
    const j = idx + delta
    if (j < 0 || j >= node.children.length) return node
    const arr = node.children.slice()
    const tmp = arr[idx]
    arr[idx] = arr[j]
    arr[j] = tmp
    return { ...node, children: renumber(arr) }
  }
  let changed = false
  const nc = node.children.map((c) => {
    const r = moveNode(c, id, delta)
    if (r !== c) changed = true
    return r
  })
  return changed ? { ...node, children: nc } : node
}

// A fresh field node with a kind-correct empty value. `key` is a slug seed;
// callers that append into a group should use addField (which de-dupes keys).
export function makeField({ name, kind }) {
  const k = kind || 'text'
  return {
    type: 'field', id: newId(), name: name || '', key: slugify(name),
    order: 0, visible: true, kind: k,
    value: k === 'bullets' || k === 'taglist' ? [] : '',
    llm_output: false, llm_instructions: '', llm_input: false,
    regen_lock: false, min: null, max: null,
  }
}

// Append a new field to the group with `groupId`, giving it a key unique within
// that group, and renumber the group's fields.
export function addField(tree, groupId, { name, kind }) {
  return updateNode(tree, groupId, (g) => {
    const existing = g.children.map((f) => f.key)
    const field = { ...makeField({ name, kind }), key: uniqueKey(slugify(name), existing) }
    return { ...g, children: renumber([...g.children, field]) }
  })
}

// Deep-clone a node subtree, assigning every node a fresh id.
function cloneWithFreshIds(node) {
  const next = { ...node, id: newId() }
  if (Array.isArray(node.children)) {
    next.children = node.children.map(cloneWithFreshIds)
  }
  if (node.item_template) {
    next.item_template = cloneWithFreshIds(node.item_template)
  }
  return next
}

// Append a fresh item (cloned from item_template, fresh ids) to the list with
// `listId` and renumber its items.
export function addListItem(tree, listId) {
  return updateNode(tree, listId, (list) => {
    const item = cloneWithFreshIds(list.item_template)
    return { ...list, children: renumber([...list.children, item]) }
  })
}

// Append a custom (role:null) section holding exactly one empty group (the
// section "exactly one child" invariant), and renumber root sections.
export function addCustomSection(tree, name) {
  const section = {
    type: 'section', id: newId(), name: name || 'Section', role: null,
    order: tree.children.length, visible: true,
    children: [{
      type: 'group', id: newId(), name: name || 'Section', order: 0,
      visible: true, regen_lock: false, children: [],
    }],
  }
  return { ...tree, children: renumber([...tree.children, section]) }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test -- treeOps`
Expected: PASS (all describe blocks green).

- [ ] **Step 5: Commit**

```bash
git add react-dashboard/src/components/widgets/profile-tree/treeOps.js react-dashboard/src/components/widgets/profile-tree/treeOps.test.js
git commit -m "[feat] Add pure profile-tree mutation helpers"
```

---

### Task 4: Field widgets

**Files:**
- Create: `react-dashboard/src/components/widgets/profile-tree/fieldWidgets.jsx`
- Create: `react-dashboard/src/components/widgets/profile-tree/fieldWidgets.test.jsx`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `FieldWidget({ field, onChange })` — dispatches on `field.kind`; calls `onChange(newValue)` where `newValue` is a string (`text`/`markdown`) or `string[]` (`bullets`/`taglist`).
  - Named sub-widgets `TextField`, `MarkdownField`, `BulletsField`, `TagListField`, each `({ value, onChange })`.

- [ ] **Step 1: Write the failing test**

Create `react-dashboard/src/components/widgets/profile-tree/fieldWidgets.test.jsx`:

```jsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { FieldWidget } from './fieldWidgets'

const field = (over) => ({
  type: 'field', id: 'f', name: 'X', key: 'x', kind: 'text', value: '',
  visible: true, ...over,
})

describe('FieldWidget', () => {
  it('text: emits string on change', () => {
    const onChange = vi.fn()
    render(<FieldWidget field={field({ kind: 'text', value: 'a' })} onChange={onChange} />)
    fireEvent.change(screen.getByDisplayValue('a'), { target: { value: 'ab' } })
    expect(onChange).toHaveBeenLastCalledWith('ab')
  })

  it('markdown: renders a textarea and emits string', () => {
    const onChange = vi.fn()
    render(<FieldWidget field={field({ kind: 'markdown', value: 'hi' })} onChange={onChange} />)
    const ta = screen.getByRole('textbox')
    expect(ta.tagName).toBe('TEXTAREA')
    fireEvent.change(ta, { target: { value: 'hey' } })
    expect(onChange).toHaveBeenLastCalledWith('hey')
  })

  it('bullets: add and remove a line emit string[]', () => {
    const onChange = vi.fn()
    render(<FieldWidget field={field({ kind: 'bullets', value: ['one'] })} onChange={onChange} />)
    fireEvent.click(screen.getByText('+ Add bullet'))
    expect(onChange).toHaveBeenLastCalledWith(['one', ''])
    onChange.mockClear()
    fireEvent.click(screen.getByLabelText('Remove bullet 1'))
    expect(onChange).toHaveBeenLastCalledWith([])
  })

  it('bullets: editing a line emits the updated array', () => {
    const onChange = vi.fn()
    render(<FieldWidget field={field({ kind: 'bullets', value: ['one'] })} onChange={onChange} />)
    fireEvent.change(screen.getByDisplayValue('one'), { target: { value: 'two' } })
    expect(onChange).toHaveBeenLastCalledWith(['two'])
  })

  it('taglist: add via Enter and remove a chip emit string[]', () => {
    const onChange = vi.fn()
    render(<FieldWidget field={field({ kind: 'taglist', value: ['Python'] })} onChange={onChange} />)
    const input = screen.getByPlaceholderText('Add…')
    fireEvent.change(input, { target: { value: 'SQL' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(onChange).toHaveBeenLastCalledWith(['Python', 'SQL'])
    onChange.mockClear()
    fireEvent.click(screen.getByLabelText('Remove Python'))
    expect(onChange).toHaveBeenLastCalledWith([])
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- fieldWidgets`
Expected: FAIL — `./fieldWidgets` not found.

- [ ] **Step 3: Write the implementation**

Create `react-dashboard/src/components/widgets/profile-tree/fieldWidgets.jsx`:

```jsx
import { useState } from 'react'

const inputClass =
  'w-full bg-white/5 border border-space-border rounded-lg px-3 py-2 text-sm text-space-text placeholder-space-dim focus:outline-none focus:border-purple-500 transition-colors'

export function TextField({ value, onChange }) {
  return (
    <input
      type="text" className={inputClass} value={value ?? ''}
      onChange={(e) => onChange(e.target.value)}
    />
  )
}

export function MarkdownField({ value, onChange }) {
  return (
    <textarea
      className={`${inputClass} min-h-[80px] resize-y`} value={value ?? ''}
      onChange={(e) => onChange(e.target.value)}
    />
  )
}

export function BulletsField({ value, onChange }) {
  const arr = Array.isArray(value) ? value : []
  const setAt = (i, v) => onChange(arr.map((x, j) => (j === i ? v : x)))
  const removeAt = (i) => onChange(arr.filter((_, j) => j !== i))
  return (
    <div className="flex flex-col gap-2">
      {arr.map((line, i) => (
        <div key={i} className="flex items-center gap-2">
          <input
            type="text" className={inputClass} value={line}
            onChange={(e) => setAt(i, e.target.value)}
          />
          <button
            type="button" aria-label={`Remove bullet ${i + 1}`}
            className="text-space-dim hover:text-red-400 px-1"
            onClick={() => removeAt(i)}
          >✕</button>
        </div>
      ))}
      <button
        type="button"
        className="self-start text-xs text-purple-400 hover:text-purple-300"
        onClick={() => onChange([...arr, ''])}
      >+ Add bullet</button>
    </div>
  )
}

export function TagListField({ value, onChange }) {
  const arr = Array.isArray(value) ? value : []
  const [draft, setDraft] = useState('')
  const add = () => {
    const t = draft.trim()
    if (!t) return
    onChange([...arr, t])
    setDraft('')
  }
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-1.5">
        {arr.map((tag, i) => (
          <span
            key={i}
            className="inline-flex items-center gap-1 bg-purple-500/15 text-purple-200 text-xs rounded-full px-2 py-0.5"
          >
            {tag}
            <button
              type="button" aria-label={`Remove ${tag}`}
              className="hover:text-red-300"
              onClick={() => onChange(arr.filter((_, j) => j !== i))}
            >✕</button>
          </span>
        ))}
      </div>
      <input
        type="text" className={inputClass} placeholder="Add…" value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); add() } }}
        onBlur={add}
      />
    </div>
  )
}

export function FieldWidget({ field, onChange }) {
  switch (field.kind) {
    case 'markdown': return <MarkdownField value={field.value} onChange={onChange} />
    case 'bullets': return <BulletsField value={field.value} onChange={onChange} />
    case 'taglist': return <TagListField value={field.value} onChange={onChange} />
    case 'text':
    default: return <TextField value={field.value} onChange={onChange} />
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test -- fieldWidgets`
Expected: PASS (5 tests).

Note: `TagListField` also adds on blur; the remove-chip test clicks before any blur-add fires, so the assertions hold. If a future edit makes blur fire spuriously in tests, assert on `onChange.mock.calls` explicitly.

- [ ] **Step 5: Commit**

```bash
git add react-dashboard/src/components/widgets/profile-tree/fieldWidgets.jsx react-dashboard/src/components/widgets/profile-tree/fieldWidgets.test.jsx
git commit -m "[feat] Add kind-aware profile field widgets"
```

---

### Task 5: Structural controls

**Files:**
- Create: `react-dashboard/src/components/widgets/profile-tree/structuralControls.jsx`
- Create: `react-dashboard/src/components/widgets/profile-tree/structuralControls.test.jsx`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `MoveButtons({ canUp, canDown, onUp, onDown })`
  - `VisibleToggle({ visible, onToggle })` — button with `aria-label` "Hide"/"Show".
  - `RenameLabel({ name, editable, onRename })` — click-to-edit label; commits on Enter/blur, cancels on Escape; static text when `!editable`.
  - `RemoveButton({ onRemove, label })` — two-click confirm (first click shows "Confirm?", second calls `onRemove`).
  - `AddButton({ label, onClick })`

- [ ] **Step 1: Write the failing test**

Create `react-dashboard/src/components/widgets/profile-tree/structuralControls.test.jsx`:

```jsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MoveButtons, VisibleToggle, RenameLabel, RemoveButton, AddButton } from './structuralControls'

describe('MoveButtons', () => {
  it('disables up at top and down at bottom', () => {
    const onUp = vi.fn(); const onDown = vi.fn()
    render(<MoveButtons canUp={false} canDown onUp={onUp} onDown={onDown} />)
    fireEvent.click(screen.getByLabelText('Move up'))
    expect(onUp).not.toHaveBeenCalled()
    fireEvent.click(screen.getByLabelText('Move down'))
    expect(onDown).toHaveBeenCalled()
  })
})

describe('VisibleToggle', () => {
  it('toggles and labels by state', () => {
    const onToggle = vi.fn()
    render(<VisibleToggle visible onToggle={onToggle} />)
    fireEvent.click(screen.getByLabelText('Hide'))
    expect(onToggle).toHaveBeenCalled()
  })
})

describe('RenameLabel', () => {
  it('commits on Enter when editable', () => {
    const onRename = vi.fn()
    render(<RenameLabel name="Old" editable onRename={onRename} />)
    fireEvent.click(screen.getByText('Old'))
    const input = screen.getByDisplayValue('Old')
    fireEvent.change(input, { target: { value: 'New' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(onRename).toHaveBeenLastCalledWith('New')
  })

  it('cancels on Escape', () => {
    const onRename = vi.fn()
    render(<RenameLabel name="Old" editable onRename={onRename} />)
    fireEvent.click(screen.getByText('Old'))
    const input = screen.getByDisplayValue('Old')
    fireEvent.change(input, { target: { value: 'X' } })
    fireEvent.keyDown(input, { key: 'Escape' })
    expect(onRename).not.toHaveBeenCalled()
    expect(screen.getByText('Old')).toBeInTheDocument()
  })

  it('is static when not editable', () => {
    render(<RenameLabel name="Fixed" editable={false} onRename={vi.fn()} />)
    fireEvent.click(screen.getByText('Fixed'))
    expect(screen.queryByDisplayValue('Fixed')).toBeNull()
  })
})

describe('RemoveButton', () => {
  it('requires a confirm click', () => {
    const onRemove = vi.fn()
    render(<RemoveButton onRemove={onRemove} label="Remove section" />)
    fireEvent.click(screen.getByLabelText('Remove section'))
    expect(onRemove).not.toHaveBeenCalled()
    fireEvent.click(screen.getByText('Confirm?'))
    expect(onRemove).toHaveBeenCalled()
  })
})

describe('AddButton', () => {
  it('fires onClick', () => {
    const onClick = vi.fn()
    render(<AddButton label="+ Add field" onClick={onClick} />)
    fireEvent.click(screen.getByText('+ Add field'))
    expect(onClick).toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- structuralControls`
Expected: FAIL — module not found.

- [ ] **Step 3: Write the implementation**

Create `react-dashboard/src/components/widgets/profile-tree/structuralControls.jsx`:

```jsx
import { useState } from 'react'

const iconBtn = 'px-1.5 py-0.5 text-space-dim hover:text-space-text disabled:opacity-30 disabled:cursor-not-allowed transition-colors'

export function MoveButtons({ canUp, canDown, onUp, onDown }) {
  return (
    <span className="inline-flex">
      <button type="button" aria-label="Move up" className={iconBtn}
        disabled={!canUp} onClick={() => canUp && onUp()}>↑</button>
      <button type="button" aria-label="Move down" className={iconBtn}
        disabled={!canDown} onClick={() => canDown && onDown()}>↓</button>
    </span>
  )
}

export function VisibleToggle({ visible, onToggle }) {
  return (
    <button
      type="button" aria-label={visible ? 'Hide' : 'Show'} className={iconBtn}
      onClick={onToggle}
    >{visible ? '👁' : '🚫'}</button>
  )
}

export function RenameLabel({ name, editable, onRename }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(name)
  if (!editable) {
    return <span className="text-sm font-semibold text-space-text">{name}</span>
  }
  if (!editing) {
    return (
      <button
        type="button"
        className="text-sm font-semibold text-space-text hover:text-purple-300"
        onClick={() => { setDraft(name); setEditing(true) }}
      >{name}</button>
    )
  }
  const commit = () => { setEditing(false); if (draft !== name) onRename(draft) }
  return (
    <input
      autoFocus type="text" value={draft}
      className="bg-white/5 border border-space-border rounded px-2 py-0.5 text-sm text-space-text"
      onChange={(e) => setDraft(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === 'Enter') commit()
        else if (e.key === 'Escape') setEditing(false)
      }}
      onBlur={commit}
    />
  )
}

export function RemoveButton({ onRemove, label }) {
  const [confirm, setConfirm] = useState(false)
  if (confirm) {
    return (
      <button
        type="button"
        className="text-xs text-red-400 hover:text-red-300 px-1.5"
        onClick={onRemove}
        onMouseLeave={() => setConfirm(false)}
      >Confirm?</button>
    )
  }
  return (
    <button
      type="button" aria-label={label} className={iconBtn}
      onClick={() => setConfirm(true)}
    >✕</button>
  )
}

export function AddButton({ label, onClick }) {
  return (
    <button
      type="button"
      className="self-start text-xs text-purple-400 hover:text-purple-300"
      onClick={onClick}
    >{label}</button>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test -- structuralControls`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add react-dashboard/src/components/widgets/profile-tree/structuralControls.jsx react-dashboard/src/components/widgets/profile-tree/structuralControls.test.jsx
git commit -m "[feat] Add profile-tree structural controls"
```

---

### Task 6: Recursive `TreeNode` renderer

**Files:**
- Create: `react-dashboard/src/components/widgets/profile-tree/TreeNode.jsx`
- Create: `react-dashboard/src/components/widgets/profile-tree/TreeNode.test.jsx`

**Interfaces:**
- Consumes: `FieldWidget` (Task 4); `MoveButtons`, `VisibleToggle`, `RenameLabel`, `RemoveButton`, `AddButton` (Task 5); `isPresetSection` (Task 3).
- Produces:
  - `SectionView({ section, isFirst, isLast, ops })` — the top-level per-section renderer. `ops` is the handler bundle (see below), all addressing nodes by `id`.
  - `ops` shape (provided by Task 7, asserted here via mocks):
    `{ setValue(id, value), rename(id, name), toggleVisible(id), remove(id), move(id, delta), addItem(listId), addField(groupId, {name, kind}) }`.

- [ ] **Step 1: Write the failing test**

Create `react-dashboard/src/components/widgets/profile-tree/TreeNode.test.jsx`:

```jsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { SectionView } from './TreeNode'

function noopOps(over = {}) {
  return {
    setValue: vi.fn(), rename: vi.fn(), toggleVisible: vi.fn(), remove: vi.fn(),
    move: vi.fn(), addItem: vi.fn(), addField: vi.fn(), ...over,
  }
}

const presetListSection = {
  type: 'section', id: 'sec-exp', name: 'Experience', role: 'experience',
  order: 1, visible: true, children: [{
    type: 'list', id: 'list-exp', name: 'Experience', order: 0, visible: true,
    bullet_style: 'none',
    item_template: { type: 'group', id: 'tmpl', name: 'E', order: 0, visible: true,
      regen_lock: false, children: [
        { type: 'field', id: 'tf', name: 'Company', key: 'company', order: 0,
          visible: true, kind: 'text', value: '' }] },
    children: [{ type: 'group', id: 'item-0', name: 'E', order: 0, visible: true,
      regen_lock: false, children: [
        { type: 'field', id: 'i0', name: 'Company', key: 'company', order: 0,
          visible: true, kind: 'text', value: 'Acme' }] }],
  }],
}

const customSection = {
  type: 'section', id: 'sec-c', name: 'Awards', role: null, order: 2, visible: true,
  children: [{ type: 'group', id: 'g-c', name: 'Awards', order: 0, visible: true,
    regen_lock: false, children: [
      { type: 'field', id: 'fa', name: 'Award', key: 'award', order: 0,
        visible: true, kind: 'text', value: 'Winner' }] }],
}

describe('SectionView preset', () => {
  it('renders no remove button and no add-field on a preset section', () => {
    render(<SectionView section={presetListSection} isFirst={false} isLast ops={noopOps()} />)
    expect(screen.queryByLabelText('Remove section')).toBeNull()
    expect(screen.queryByText('+ Add field')).toBeNull()
  })

  it('allows adding and removing list items on a preset list', () => {
    const ops = noopOps()
    render(<SectionView section={presetListSection} isFirst={false} isLast ops={ops} />)
    fireEvent.click(screen.getByText('+ Add entry'))
    expect(ops.addItem).toHaveBeenCalledWith('list-exp')
    fireEvent.click(screen.getByLabelText('Remove item'))
    fireEvent.click(screen.getByText('Confirm?'))
    expect(ops.remove).toHaveBeenCalledWith('item-0')
  })

  it('edits a field value through ops.setValue', () => {
    const ops = noopOps()
    render(<SectionView section={presetListSection} isFirst={false} isLast ops={ops} />)
    fireEvent.change(screen.getByDisplayValue('Acme'), { target: { value: 'Acme2' } })
    expect(ops.setValue).toHaveBeenLastCalledWith('i0', 'Acme2')
  })
})

describe('SectionView custom', () => {
  it('renders remove + add-field controls and wires them by id', () => {
    const ops = noopOps()
    render(<SectionView section={customSection} isFirst isLast={false} ops={ops} />)
    fireEvent.click(screen.getByLabelText('Remove section'))
    fireEvent.click(screen.getByText('Confirm?'))
    expect(ops.remove).toHaveBeenCalledWith('sec-c')
  })

  it('toggles section visibility by id', () => {
    const ops = noopOps()
    render(<SectionView section={customSection} isFirst isLast={false} ops={ops} />)
    fireEvent.click(screen.getByLabelText('Hide'))
    expect(ops.toggleVisible).toHaveBeenCalledWith('sec-c')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- TreeNode`
Expected: FAIL — `./TreeNode` not found.

- [ ] **Step 3: Write the implementation**

Create `react-dashboard/src/components/widgets/profile-tree/TreeNode.jsx`:

```jsx
import { useState } from 'react'
import { FieldWidget } from './fieldWidgets'
import { MoveButtons, VisibleToggle, RenameLabel, RemoveButton, AddButton } from './structuralControls'
import { isPresetSection } from './treeOps'

const rowWrap = 'flex flex-col gap-1'
const headerRow = 'flex items-center justify-between gap-2'

// A single field: label (renamable only on custom groups) + visible + widget.
function FieldView({ field, fieldsEditable, ops }) {
  return (
    <div className={rowWrap}>
      <div className={headerRow}>
        <RenameLabel
          name={field.name} editable={fieldsEditable}
          onRename={(n) => ops.rename(field.id, n)}
        />
        <VisibleToggle visible={field.visible} onToggle={() => ops.toggleVisible(field.id)} />
      </div>
      <div className={field.visible ? '' : 'opacity-50'}>
        <FieldWidget field={field} onChange={(v) => ops.setValue(field.id, v)} />
      </div>
    </div>
  )
}

// A group's fields. `fieldsEditable` enables rename + add/remove field (custom only).
function GroupView({ group, fieldsEditable, ops }) {
  return (
    <div className="flex flex-col gap-3">
      {group.children.map((f) => (
        <div key={f.id} className="flex items-start gap-2">
          <div className="flex-1">
            <FieldView field={f} fieldsEditable={fieldsEditable} ops={ops} />
          </div>
          {fieldsEditable && (
            <RemoveButton onRemove={() => ops.remove(f.id)} label="Remove field" />
          )}
        </div>
      ))}
      {fieldsEditable && <AddFieldForm groupId={group.id} ops={ops} />}
    </div>
  )
}

function AddFieldForm({ groupId, ops }) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [kind, setKind] = useState('text')
  if (!open) return <AddButton label="+ Add field" onClick={() => setOpen(true)} />
  return (
    <div className="flex items-center gap-2">
      <input
        type="text" placeholder="Field name" value={name}
        className="bg-white/5 border border-space-border rounded px-2 py-1 text-sm text-space-text"
        onChange={(e) => setName(e.target.value)}
      />
      <select
        value={kind} onChange={(e) => setKind(e.target.value)}
        className="bg-white/5 border border-space-border rounded px-2 py-1 text-sm text-space-text"
      >
        <option value="text">text</option>
        <option value="markdown">markdown</option>
        <option value="bullets">bullets</option>
        <option value="taglist">taglist</option>
      </select>
      <button
        type="button" className="text-xs text-purple-400 hover:text-purple-300"
        onClick={() => { if (name.trim()) { ops.addField(groupId, { name: name.trim(), kind }); setName(''); setOpen(false) } }}
      >Add</button>
      <button
        type="button" className="text-xs text-space-dim hover:text-space-text"
        onClick={() => { setName(''); setOpen(false) }}
      >Cancel</button>
    </div>
  )
}

// A repeating list: each item is a fixed-shape group (no field add/remove);
// items can be added (clone template), removed, and reordered.
function ListView({ list, ops }) {
  return (
    <div className="flex flex-col gap-4">
      {list.children.map((item, i) => (
        <div key={item.id} className="border border-space-border/50 rounded-lg p-3 flex flex-col gap-2">
          <div className={headerRow}>
            <span className="text-xs text-space-dim">Entry {i + 1}</span>
            <span className="inline-flex items-center">
              <MoveButtons
                canUp={i > 0} canDown={i < list.children.length - 1}
                onUp={() => ops.move(item.id, -1)} onDown={() => ops.move(item.id, 1)}
              />
              <RemoveButton onRemove={() => ops.remove(item.id)} label="Remove item" />
            </span>
          </div>
          <GroupView group={item} fieldsEditable={false} ops={ops} />
        </div>
      ))}
      <AddButton label="+ Add entry" onClick={() => ops.addItem(list.id)} />
    </div>
  )
}

// The single child of a section is a group, list, or field.
function SectionChild({ child, preset, ops }) {
  if (child.type === 'list') return <ListView list={child} ops={ops} />
  if (child.type === 'group') return <GroupView group={child} fieldsEditable={!preset} ops={ops} />
  // bare field child (e.g. summary hero, skills taglist)
  return <FieldView field={child} fieldsEditable={false} ops={ops} />
}

export function SectionView({ section, isFirst, isLast, ops }) {
  const preset = isPresetSection(section)
  const child = section.children[0]
  return (
    <div className={`border border-space-border rounded-xl p-4 flex flex-col gap-3 ${section.visible ? '' : 'opacity-60'}`}>
      <div className={headerRow}>
        <RenameLabel
          name={section.name} editable
          onRename={(n) => ops.rename(section.id, n)}
        />
        <span className="inline-flex items-center gap-1">
          <MoveButtons
            canUp={!isFirst} canDown={!isLast}
            onUp={() => ops.move(section.id, -1)} onDown={() => ops.move(section.id, 1)}
          />
          <VisibleToggle visible={section.visible} onToggle={() => ops.toggleVisible(section.id)} />
          {!preset && <RemoveButton onRemove={() => ops.remove(section.id)} label="Remove section" />}
        </span>
      </div>
      {child && <SectionChild child={child} preset={preset} ops={ops} />}
    </div>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test -- TreeNode`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add react-dashboard/src/components/widgets/profile-tree/TreeNode.jsx react-dashboard/src/components/widgets/profile-tree/TreeNode.test.jsx
git commit -m "[feat] Add recursive profile TreeNode renderer"
```

---

### Task 7: `ProfileTreeEditor` (state, save, 422)

**Files:**
- Create: `react-dashboard/src/components/widgets/profile-tree/ProfileTreeEditor.jsx`
- Create: `react-dashboard/src/components/widgets/profile-tree/ProfileTreeEditor.test.jsx`

**Interfaces:**
- Consumes: `getProfileTree`, `putProfileTree` (Task 2); `SectionView` (Task 6); `updateNode`, `removeNode`, `moveNode`, `addField`, `addListItem`, `addCustomSection` (Task 3).
- Produces: `default ProfileTreeEditor({ profileId })` — loads the tree, renders sections, owns dirty state + Save/Discard + 422 surfacing.

- [ ] **Step 1: Write the failing test**

Create `react-dashboard/src/components/widgets/profile-tree/ProfileTreeEditor.test.jsx`:

```jsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import ProfileTreeEditor from './ProfileTreeEditor'
import * as api from '../../../api'

vi.mock('../../../api')

function serverTree() {
  return {
    type: 'root', id: 'r', children: [{
      type: 'section', id: 'sec-skills', name: 'Skills', role: 'skills',
      order: 0, visible: true, children: [{
        type: 'field', id: 'f-skills', name: 'Skills', key: 'skills', order: 0,
        visible: true, kind: 'taglist', value: ['Python'],
        llm_output: false, llm_instructions: '', llm_input: false,
        regen_lock: false, min: null, max: null }],
    }],
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  api.getProfileTree.mockResolvedValue({ tree: serverTree() })
  api.putProfileTree.mockImplementation(async (_id, tree) => ({ tree }))
})

describe('ProfileTreeEditor', () => {
  it('loads and renders sections', async () => {
    render(<ProfileTreeEditor profileId={1} />)
    expect(await screen.findByText('Skills')).toBeInTheDocument()
    expect(screen.getByText('Python')).toBeInTheDocument()
  })

  it('an edit sets dirty; Save PUTs the tree and clears dirty', async () => {
    render(<ProfileTreeEditor profileId={1} />)
    await screen.findByText('Skills')
    expect(screen.getByText('Save').closest('button')).toBeDisabled()
    fireEvent.click(screen.getByLabelText('Remove Python'))
    expect(screen.getByText('Save').closest('button')).not.toBeDisabled()
    fireEvent.click(screen.getByText('Save'))
    await waitFor(() => expect(api.putProfileTree).toHaveBeenCalledTimes(1))
    const [, sentTree] = api.putProfileTree.mock.calls[0]
    const skills = sentTree.children[0].children[0]
    expect(skills.value).toEqual([])
    await waitFor(() => expect(screen.getByText('Save').closest('button')).toBeDisabled())
  })

  it('Discard reverts edits', async () => {
    render(<ProfileTreeEditor profileId={1} />)
    await screen.findByText('Skills')
    fireEvent.click(screen.getByLabelText('Remove Python'))
    fireEvent.click(screen.getByText('Discard'))
    expect(screen.getByText('Python')).toBeInTheDocument()
    expect(screen.getByText('Save').closest('button')).toBeDisabled()
  })

  it('surfaces a 422 message and keeps edits', async () => {
    api.putProfileTree.mockRejectedValueOnce(new Error('PUT /api/config/profiles/1/tree → 422'))
    render(<ProfileTreeEditor profileId={1} />)
    await screen.findByText('Skills')
    fireEvent.click(screen.getByLabelText('Remove Python'))
    fireEvent.click(screen.getByText('Save'))
    expect(await screen.findByText(/could not be saved/i)).toBeInTheDocument()
    // still dirty (edit preserved)
    expect(screen.getByText('Save').closest('button')).not.toBeDisabled()
  })

  it('adds a custom section', async () => {
    render(<ProfileTreeEditor profileId={1} />)
    await screen.findByText('Skills')
    fireEvent.click(screen.getByText('+ Add section'))
    expect(await screen.findByText('New section')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- ProfileTreeEditor`
Expected: FAIL — `./ProfileTreeEditor` not found.

- [ ] **Step 3: Write the implementation**

Create `react-dashboard/src/components/widgets/profile-tree/ProfileTreeEditor.jsx`:

```jsx
import { useState, useEffect, useCallback } from 'react'
import { getProfileTree, putProfileTree } from '../../../api'
import { SectionView } from './TreeNode'
import {
  updateNode, removeNode, moveNode, addField, addListItem, addCustomSection,
} from './treeOps'

export default function ProfileTreeEditor({ profileId }) {
  const [tree, setTree] = useState(null)
  const [saved, setSaved] = useState(null) // last-persisted snapshot for Discard
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true); setLoadError(null)
    getProfileTree(profileId)
      .then(({ tree: t }) => { if (!cancelled) { setTree(t); setSaved(t) } })
      .catch(() => { if (!cancelled) setLoadError('Failed to load profile') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [profileId])

  const dirty = tree !== saved

  // Handler bundle passed to SectionView; all address nodes by id.
  const ops = {
    setValue: useCallback((id, value) => setTree((t) => updateNode(t, id, (n) => ({ ...n, value }))), []),
    rename: useCallback((id, name) => setTree((t) => updateNode(t, id, (n) => ({ ...n, name }))), []),
    toggleVisible: useCallback((id) => setTree((t) => updateNode(t, id, (n) => ({ ...n, visible: !n.visible }))), []),
    remove: useCallback((id) => setTree((t) => removeNode(t, id)), []),
    move: useCallback((id, delta) => setTree((t) => moveNode(t, id, delta)), []),
    addItem: useCallback((listId) => setTree((t) => addListItem(t, listId)), []),
    addField: useCallback((groupId, spec) => setTree((t) => addField(t, groupId, spec)), []),
  }

  const handleSave = async () => {
    setSaving(true); setSaveError(null)
    try {
      const { tree: persisted } = await putProfileTree(profileId, tree)
      setTree(persisted); setSaved(persisted)
    } catch (e) {
      const is422 = String(e?.message || '').includes('422')
      setSaveError(
        is422
          ? 'Your changes could not be saved — the profile structure is invalid (check section/field limits).'
          : 'Save failed. Please try again.',
      )
    } finally {
      setSaving(false)
    }
  }

  const handleDiscard = () => { setTree(saved); setSaveError(null) }

  if (loading) return <p className="text-xs text-space-dim">Loading…</p>
  if (loadError) return <p className="text-xs text-red-400">{loadError}</p>
  if (!tree) return null

  const sections = tree.children
  return (
    <div className="flex flex-col gap-3">
      {sections.map((section, i) => (
        <SectionView
          key={section.id} section={section}
          isFirst={i === 0} isLast={i === sections.length - 1} ops={ops}
        />
      ))}

      <button
        type="button"
        className="self-start text-xs text-purple-400 hover:text-purple-300 mt-1"
        onClick={() => setTree((t) => addCustomSection(t, 'New section'))}
      >+ Add section</button>

      {saveError && <p className="text-xs text-red-400">{saveError}</p>}

      <div className="sticky bottom-0 flex items-center gap-2 bg-[#0f0f1a]/90 backdrop-blur py-2">
        <button
          type="button" onClick={handleSave} disabled={!dirty || saving}
          className="px-4 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-semibold transition-colors"
        >{saving ? 'Saving…' : 'Save'}</button>
        <button
          type="button" onClick={handleDiscard} disabled={!dirty || saving}
          className="px-4 py-2 rounded-lg border border-space-border text-sm text-space-dim hover:text-space-text disabled:opacity-40 transition-colors"
        >Discard</button>
        {dirty && <span className="text-xs text-space-dim">Unsaved changes</span>}
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test -- ProfileTreeEditor`
Expected: PASS (5 tests).

- [ ] **Step 5: Run the whole frontend suite**

Run (from `react-dashboard/`): `npm run test`
Expected: PASS (all suites: harness, api, treeOps, fieldWidgets, structuralControls, TreeNode, ProfileTreeEditor).

- [ ] **Step 6: Commit**

```bash
git add react-dashboard/src/components/widgets/profile-tree/ProfileTreeEditor.jsx react-dashboard/src/components/widgets/profile-tree/ProfileTreeEditor.test.jsx
git commit -m "[feat] Add ProfileTreeEditor with save/discard and 422 handling"
```

---

### Task 8: Integrate into `ProfileDetail` + retire dead code + docs

**Files:**
- Modify: `react-dashboard/src/components/widgets/ProfileDetail.jsx`
- Modify: `react-dashboard/CONTEXT.md`, `core/CONTEXT.md`

**Interfaces:**
- Consumes: `ProfileTreeEditor` (Task 7).
- Produces: the live profile editor now renders the tree editor in place of the six doc-section accordions. No new exported interface.

- [ ] **Step 1: Swap the render region**

In `react-dashboard/src/components/widgets/ProfileDetail.jsx`, add the import near the top (after the existing imports):

```jsx
import ProfileTreeEditor from './profile-tree/ProfileTreeEditor'
```

In `ProfileDetailView`'s returned JSX, replace these six lines:

```jsx
        <ProfileSection data={d} onSave={handleSave} />
        <ContactSection data={d} onSave={handleSave} />
        <SkillsSection data={d} onSave={handleSave} />
        <ExperienceSection data={d} onSave={handleSave} />
        <EducationSection data={d} onSave={handleSave} />
        <ProjectsSection data={d} onSave={handleSave} />
```

with:

```jsx
        <ProfileTreeEditor profileId={profileId} />
```

Leave `<PromptsSection .../>`, the Export Master button, and Reset Profile flow unchanged.

- [ ] **Step 2: Delete the now-dead section components**

Remove the six section components and the helpers that only served them, now that nothing references them:
- The component functions `ProfileSection`, `ContactSection`, `SkillsSection`, `ExperienceSection`, `EducationSection`, `ProjectsSection`.
- The `isSectionEmpty` helper (only used by those sections).
- Any helper used **exclusively** by the deleted components (e.g. a local `EditBtn`/edit-modal/`fieldRenderer` used only by them). Keep anything still referenced by `PromptsSection`, `ProfileDetailView`, or the shared exports (`inputClass`, `useEscape`, `ChevronDown`, `AccordionSection` if `PromptsSection` uses it).

Verification that nothing dangling remains:

```bash
cd react-dashboard
npx eslint src/components/widgets/ProfileDetail.jsx
```

Expected: no `no-undef` / `no-unused-vars` errors. Fix any unused-import or undefined-reference fallout from the deletions until clean.

- [ ] **Step 3: Build to confirm the app still compiles**

Run (from `react-dashboard/`): `npm run build`
Expected: build succeeds with no errors.

- [ ] **Step 4: Run the full frontend suite**

Run (from `react-dashboard/`): `npm run test`
Expected: PASS (all suites green; no test imported a deleted symbol).

- [ ] **Step 5: Manual verification (record results in the report)**

Start the app (`start.bat dev` from repo root) and, in the dashboard's profile editor:
1. Confirm the profile renders as tree sections (header/summary/experience/education/projects/skills) with the existing data.
2. Edit a skills tag and a header field; add an experience entry; add a custom "Awards" section with a text field; reorder a section; hide a section.
3. Click **Save**; reload the page; confirm all edits (incl. the custom section) persisted and the experience entry's id-bearing data is intact.
4. Confirm name + Prompts + Export Master + Reset still work.

Record the observed outcome (pass/fail per step) in the task report. If a step fails, treat it as a blocking bug and fix before commit.

- [ ] **Step 6: Update docs**

In `react-dashboard/CONTEXT.md`, update the ProfileDetail routing rows: the profile doc-section editor is now `components/widgets/profile-tree/ProfileTreeEditor.jsx` (tree-driven, whole-tree Save via `PUT /api/config/profiles/{id}/tree`); `ProfileDetail.jsx` retains name/Prompts/Export/Reset only. Note the new `profile-tree/` module (treeOps, fieldWidgets, structuralControls, TreeNode) and that the dashboard now has a Vitest suite (`npm run test`).

In `core/CONTEXT.md` → "Profile Schema Engine", add a line: sub-project **2B** ships the tree-driven editor consuming the 2A `GET`/`PUT /tree` endpoints; the flat `update_profile` endpoint is retained for name/job-preferences/onboarding (only the flat *doc-section editor UI* was retired). Custom sections remain unrendered on generated documents until #4.

- [ ] **Step 7: Commit**

```bash
git add react-dashboard/src/components/widgets/ProfileDetail.jsx react-dashboard/CONTEXT.md core/CONTEXT.md
git commit -m "[feat] Render tree-driven profile editor; retire flat doc-section UI"
```

---

## Self-Review

**Spec coverage:**
- Test harness (Vitest + RTL + jsdom) → Task 1. ✓
- API wrappers `getProfileTree`/`putProfileTree` → Task 2. ✓
- Generic recursion + kind widgets (text/markdown/bullets/taglist) → Tasks 4 (widgets) & 6 (recursion). ✓
- Structural ops (add item, add custom section + fields, rename, reorder, remove, visible) → Task 3 (logic) + Tasks 5/6/7 (UI wiring). ✓
- Preset/custom provenance protection (no preset remove, no preset field add, list-item add allowed, section single-child, unique keys, order renormalization) → Task 3 helpers + Task 6 rules; asserted in Task 3 and Task 6 tests. ✓
- Explicit Save (whole-tree PUT) + dirty + Discard + 422 surfacing + state replaced by server tree → Task 7. ✓
- Round-trip preservation of tree-only attrs (clone keeps llm_*/regen_lock/min/max/bullet_style) → Task 3 `cloneWithFreshIds`/`makeField`; the editor only sets explicit attrs via `updateNode` so others survive → covered by the 2A server tests + Task 8 manual round-trip. ✓
- Integration: replace six accordions, keep name/Prompts/preferences, keep flat `update_profile` → Task 8. ✓
- Retire flat doc-section editor UI only (not the endpoint) → Task 8 + docs. ✓
- Out-of-scope (drag-drop, gallery, doc rendering of custom sections, LLM-attr editing) → not implemented; recorded in spec. ✓

**Placeholder scan:** none — every code step contains complete code; every run step has an exact command and expected result. Task 8 Step 2 deletes code by name with an eslint gate rather than pasting the (large, to-be-deleted) section bodies, which is the correct instruction for a deletion step.

**Type/identifier consistency:** `ops` bundle keys (`setValue`, `rename`, `toggleVisible`, `remove`, `move`, `addItem`, `addField`) are identical across Task 6 (consumer) and Task 7 (producer). `treeOps` exports (`updateNode`, `removeNode`, `moveNode`, `addField`, `addListItem`, `addCustomSection`, `renumber`, `isPresetSection`, `makeField`) match their call sites in Tasks 6/7. `getProfileTree`/`putProfileTree` signatures match between Task 2 and Task 7. `FieldWidget`/`SectionView` props match between definition and use. Field `value` types (string vs string[]) consistent between widgets (Task 4) and helpers (Task 3).

**Note on a deliberate deviation:** the spec mentions retaining a "Job Preferences" accordion in `ProfileDetail`; in the current code the rendered body has no preferences accordion (target-roles UI lives in onboarding/Settings, and LLM config in `Settings.jsx`). Task 8 therefore only removes what is actually rendered (the six doc-section components) and leaves `PromptsSection`/Export/Reset intact — net behavior matches the spec's intent (keep non-doc-section UI; retire doc-section UI).
