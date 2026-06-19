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
