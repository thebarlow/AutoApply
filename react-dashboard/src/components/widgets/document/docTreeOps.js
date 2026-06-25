// Pure, immutable helpers over a tree-v1 document RootNode. Values-only: no
// structural mutation. A "node" is any object with an `id`; children live on
// `.children` (sections/lists/groups) and fields are leaves with `.kind`/`.value`.

function mapChildren(node, fn) {
  if (!node.children) return node
  let changed = false
  const next = node.children.map((c) => {
    const r = fn(c)
    if (r !== c) changed = true
    return r
  })
  return changed ? { ...node, children: next } : node
}

export function setFieldValue(root, fieldId, value) {
  const visit = (node) => {
    if (node.id === fieldId && node.type === 'field') return { ...node, value }
    return mapChildren(node, visit)
  }
  return visit(root)
}

export function owningSection(root, nodeId) {
  for (const section of root.children || []) {
    if (section.id === nodeId) return section
    const stack = [...(section.children || [])]
    while (stack.length) {
      const n = stack.pop()
      if (n.id === nodeId) return section
      if (n.children) stack.push(...n.children)
    }
  }
  return null
}

function findNode(root, nodeId) {
  const stack = [root]
  while (stack.length) {
    const n = stack.pop()
    if (n.id === nodeId) return n
    if (n.children) stack.push(...n.children)
  }
  return null
}

export function anchorLabel(root, nodeId) {
  const section = owningSection(root, nodeId)
  const node = findNode(root, nodeId)
  if (!section) return node?.name || 'Document'
  if (node && node.id !== section.id && node.name) return `${section.name} › ${node.name}`
  return section.name
}

export function sectionLocked(root, nodeId) {
  return !!owningSection(root, nodeId)?.locked
}
