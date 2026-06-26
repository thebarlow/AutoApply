import { describe, it, expect } from 'vitest'
import { setOutputFormat } from './treeOps'

const tree = {
  type: 'root', id: 'r', children: [
    { type: 'section', id: 's', role: 'experience', children: [
      { type: 'list', id: 'l', item_template: { type: 'group', id: 't', children: [] }, children: [
        { type: 'group', id: 'g', children: [
          { type: 'field', id: 'f1', key: 'summary', kind: 'markdown', value: 'x', output_format: '' },
        ] },
      ] },
    ] },
  ],
}

describe('setOutputFormat', () => {
  it('sets output_format and aligns kind on the field', () => {
    const next = setOutputFormat(tree, 'f1', 'bullets', 'bullets')
    const f = next.children[0].children[0].children[0].children[0]
    expect(f.output_format).toBe('bullets')
    expect(f.kind).toBe('bullets')
  })

  it('does not mutate the input tree', () => {
    setOutputFormat(tree, 'f1', 'bullets', 'bullets')
    const f = tree.children[0].children[0].children[0].children[0]
    expect(f.output_format).toBe('')
  })
})
