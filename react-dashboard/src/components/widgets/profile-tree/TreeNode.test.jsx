import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { SectionView } from './TreeNode'

function noopOps(over = {}) {
  return {
    setValue: vi.fn(), rename: vi.fn(), toggleVisible: vi.fn(), remove: vi.fn(),
    move: vi.fn(), addItem: vi.fn(), addField: vi.fn(),
    setInstructions: vi.fn(), toggleWritten: vi.fn(), ...over,
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
    fireEvent.click(screen.getByLabelText('Expand section')) // collapsed by default
    fireEvent.click(screen.getByText('+ Add entry'))
    expect(ops.addItem).toHaveBeenCalledWith('list-exp')
    fireEvent.click(screen.getByLabelText('Remove item'))
    fireEvent.click(screen.getByText('Confirm?'))
    expect(ops.remove).toHaveBeenCalledWith('item-0')
  })

  it('renders a drag handle per list entry', () => {
    render(<SectionView section={presetListSection} isFirst={false} isLast ops={noopOps()} />)
    fireEvent.click(screen.getByLabelText('Expand section')) // collapsed by default
    expect(screen.getAllByLabelText('Drag to reorder item')).toHaveLength(1)
  })

  it('edits a field value through ops.setValue', () => {
    const ops = noopOps()
    render(<SectionView section={presetListSection} isFirst={false} isLast ops={ops} />)
    fireEvent.click(screen.getByLabelText('Expand section')) // section collapsed by default
    fireEvent.click(screen.getByLabelText('Expand item')) // entry collapsed by default
    fireEvent.change(screen.getByDisplayValue('Acme'), { target: { value: 'Acme2' } })
    expect(ops.setValue).toHaveBeenLastCalledWith('i0', 'Acme2')
  })

  it('collapses list entries by default, showing a field-value summary', () => {
    render(<SectionView section={presetListSection} isFirst={false} isLast ops={noopOps()} />)
    fireEvent.click(screen.getByLabelText('Expand section'))
    // entry body (field) hidden; summary from first non-empty field shown
    expect(screen.queryByDisplayValue('Acme')).toBeNull()
    expect(screen.getByText('— Acme')).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Expand item'))
    expect(screen.getByDisplayValue('Acme')).toBeInTheDocument()
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

  it('is collapsed by default and expands/collapses on toggle', () => {
    render(<SectionView section={customSection} isFirst isLast={false} ops={noopOps()} />)
    // collapsed by default: the field value is not rendered
    expect(screen.queryByDisplayValue('Winner')).toBeNull()
    fireEvent.click(screen.getByLabelText('Expand section'))
    expect(screen.getByDisplayValue('Winner')).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Collapse section'))
    expect(screen.queryByDisplayValue('Winner')).toBeNull()
  })

  it('expands when the section bar (name) is single-clicked', () => {
    render(<SectionView section={customSection} isFirst isLast={false} ops={noopOps()} />)
    expect(screen.queryByDisplayValue('Winner')).toBeNull()
    fireEvent.click(screen.getByText('Awards')) // click the name, not the caret
    expect(screen.getByDisplayValue('Winner')).toBeInTheDocument()
  })

  it('renames the section only on double-click of the name', () => {
    const ops = noopOps()
    render(<SectionView section={customSection} isFirst isLast={false} ops={ops} />)
    fireEvent.doubleClick(screen.getByText('Awards'))
    const input = screen.getByDisplayValue('Awards')
    fireEvent.change(input, { target: { value: 'Honors' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(ops.rename).toHaveBeenCalledWith('sec-c', 'Honors')
  })

  it('locks a field from the LLM by default and toggles via the lock control', () => {
    const ops = noopOps()
    render(<SectionView section={customSection} isFirst isLast={false} ops={ops} />)
    fireEvent.click(screen.getByLabelText('Expand section'))
    // locked by default → no instructions box, lock offers to unlock
    expect(screen.queryByLabelText('LLM instructions')).toBeNull()
    fireEvent.click(screen.getByLabelText('Unlock for LLM to write'))
    expect(ops.toggleWritten).toHaveBeenCalledWith('fa')
  })

  it('shows the instructions box when a field is LLM-written', () => {
    const written = {
      ...customSection,
      children: [{
        ...customSection.children[0],
        children: [{ ...customSection.children[0].children[0], llm_output: true }],
      }],
    }
    render(<SectionView section={written} isFirst isLast={false} ops={noopOps()} />)
    fireEvent.click(screen.getByLabelText('Expand section'))
    expect(screen.getByLabelText('LLM instructions')).toBeInTheDocument()
    expect(screen.getByLabelText('Lock from LLM (keep as typed)')).toBeInTheDocument()
  })
})
