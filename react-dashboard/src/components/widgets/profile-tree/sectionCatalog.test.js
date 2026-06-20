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
