import { describe, it, expect } from 'vitest'
import {
  PRESET_ROLES, isPresetSection, renumber, updateNode, removeNode,
  moveNode, makeField, addField, addListItem, addCustomSection,
  cloneWithFreshIds, addSection, reorderSiblings,
  fieldRole, setFieldRole, setLlmInstructions, toggleRegenLock,
  isLlmWritten, toggleLlmWritten, deepEqual, toggleLocked, setNodePrompt, isLocked,
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
    const tmplField = next.children[1].children[0].item_template.children[0]
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

describe('field role helpers', () => {
  function tree() {
    return { type: 'root', id: 'r', children: [
      { type: 'section', id: 's', name: 'S', role: null, order: 0, visible: true, children: [
        { type: 'group', id: 'g', name: 'G', order: 0, visible: true, regen_lock: false, children: [
          { type: 'field', id: 'f', name: 'F', key: 'f', order: 0, visible: true,
            kind: 'markdown', value: '', llm_output: false, llm_instructions: '',
            llm_input: false, regen_lock: false, min: null, max: null },
        ] },
      ] },
    ] }
  }

  it('derives role from flags', () => {
    expect(fieldRole({ llm_output: true, llm_input: false })).toBe('output')
    expect(fieldRole({ llm_output: false, llm_input: true })).toBe('context')
    expect(fieldRole({ llm_output: false, llm_input: false })).toBe('immutable')
  })

  it('setFieldRole sets the flag pair and is immutable', () => {
    const t = tree()
    const out = setFieldRole(t, 'f', 'output')
    expect(out).not.toBe(t)
    const f = out.children[0].children[0].children[0]
    expect(f.llm_output).toBe(true)
    expect(f.llm_input).toBe(false)
    const ctx = setFieldRole(t, 'f', 'context').children[0].children[0].children[0]
    expect(ctx.llm_output).toBe(false)
    expect(ctx.llm_input).toBe(true)
    const imm = setFieldRole(t, 'f', 'immutable').children[0].children[0].children[0]
    expect(imm.llm_output).toBe(false)
    expect(imm.llm_input).toBe(false)
  })

  it('setLlmInstructions writes the text', () => {
    const f = setLlmInstructions(tree(), 'f', 'Rewrite punchier')
      .children[0].children[0].children[0]
    expect(f.llm_instructions).toBe('Rewrite punchier')
  })

  it('toggleRegenLock flips the lock', () => {
    const f = toggleRegenLock(tree(), 'f').children[0].children[0].children[0]
    expect(f.regen_lock).toBe(true)
  })

  it('toggleLlmWritten flips llm_output and clears llm_input, immutably', () => {
    const t = tree()
    const out = toggleLlmWritten(t, 'f')
    expect(out).not.toBe(t)
    const f = out.children[0].children[0].children[0]
    expect(f.llm_output).toBe(true)
    expect(f.llm_input).toBe(false)
    expect(isLlmWritten(f)).toBe(true)
    // toggling back locks it again
    const back = toggleLlmWritten(out, 'f').children[0].children[0].children[0]
    expect(back.llm_output).toBe(false)
    expect(isLlmWritten(back)).toBe(false)
  })
})

describe('deepEqual', () => {
  it('is true for value-equal trees regardless of identity or key order', () => {
    const a = { type: 'field', id: 'f', value: ['x', 'y'], meta: { a: 1, b: 2 } }
    const b = { id: 'f', type: 'field', meta: { b: 2, a: 1 }, value: ['x', 'y'] }
    expect(deepEqual(a, b)).toBe(true)
  })

  it('is false when a value differs, an array reorders, or a key is missing', () => {
    expect(deepEqual({ v: 1 }, { v: 2 })).toBe(false)
    expect(deepEqual({ v: ['a', 'b'] }, { v: ['b', 'a'] })).toBe(false)
    expect(deepEqual({ a: 1, b: 2 }, { a: 1 })).toBe(false)
  })
})

describe('toggleLocked / setNodePrompt', () => {
  function tree() {
    return {
      type: 'root', id: 'r', children: [{
        type: 'section', id: 's', name: 'S', role: null, order: 0, visible: true,
        locked: false, prompt: '', children: [{
          type: 'group', id: 'g', name: 'G', order: 0, visible: true,
          locked: false, prompt: '', children: [] }],
      }],
    }
  }

  it('toggles locked on a section', () => {
    const t = toggleLocked(tree(), 's')
    expect(t.children[0].locked).toBe(true)
  })

  it('toggles locked on a group', () => {
    const t = toggleLocked(tree(), 'g')
    expect(t.children[0].children[0].locked).toBe(true)
  })

  it('sets a section prompt without mutating input', () => {
    const orig = tree()
    const t = setNodePrompt(orig, 's', 'Tailor it')
    expect(t.children[0].prompt).toBe('Tailor it')
    expect(orig.children[0].prompt).toBe('')
  })

  it('isLocked reads the flag', () => {
    expect(isLocked({ locked: true })).toBe(true)
    expect(isLocked({})).toBe(false)
  })
})
