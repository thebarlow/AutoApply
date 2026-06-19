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
