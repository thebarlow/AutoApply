import { describe, it, expect } from 'vitest'
import { setFieldValue, owningSection, anchorLabel, sectionLocked } from './docTreeOps'

const root = {
  type: 'root', id: 'r', children: [
    { type: 'section', id: 's1', name: 'Summary', locked: false, children: [
      { type: 'field', id: 'f1', name: 'Summary', kind: 'markdown', value: 'old' }] },
    { type: 'section', id: 's2', name: 'Skills', locked: true, children: [
      { type: 'list', id: 'l2', name: 'Skills', children: [
        { type: 'group', id: 'g2', name: 'G', children: [
          { type: 'field', id: 'f2', name: 'Skill', kind: 'taglist', value: ['a'] }] }] }] },
  ],
}

describe('docTreeOps', () => {
  it('setFieldValue updates only the target field immutably', () => {
    const next = setFieldValue(root, 'f1', 'new')
    expect(next.children[0].children[0].value).toBe('new')
    expect(root.children[0].children[0].value).toBe('old') // original untouched
    expect(next.children[1]).toBe(root.children[1])        // untouched branch shared
  })

  it('owningSection finds the ancestor section for a deep field', () => {
    expect(owningSection(root, 'f2').id).toBe('s2')
    expect(owningSection(root, 's1').id).toBe('s1')
  })

  it('anchorLabel composes section and node names', () => {
    expect(anchorLabel(root, 'f1')).toBe('Summary › Summary')
    expect(anchorLabel(root, 's1')).toBe('Summary')
  })

  it('sectionLocked reflects the owning section lock', () => {
    expect(sectionLocked(root, 'f1')).toBe(false)
    expect(sectionLocked(root, 'f2')).toBe(true)
  })
})
