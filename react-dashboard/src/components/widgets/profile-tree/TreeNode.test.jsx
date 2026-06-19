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
    fireEvent.click(screen.getByLabelText('Hide section'))
    expect(ops.toggleVisible).toHaveBeenCalledWith('sec-c')
  })
})
