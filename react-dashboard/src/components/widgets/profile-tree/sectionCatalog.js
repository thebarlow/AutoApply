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
