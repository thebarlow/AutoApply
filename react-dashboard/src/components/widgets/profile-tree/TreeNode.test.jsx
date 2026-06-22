import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { SectionView } from './TreeNode'
import { buildChipGroups } from './PromptField' // ensures module wired

function noopOps(over = {}) {
  return {
    setValue: vi.fn(), rename: vi.fn(), toggleVisible: vi.fn(), remove: vi.fn(),
    move: vi.fn(), addItem: vi.fn(), addField: vi.fn(),
    setInstructions: vi.fn(), toggleWritten: vi.fn(),
    toggleLocked: vi.fn(), setPrompt: vi.fn(), ...over,
  }
}

function rootOf(section) {
  return { type: 'root', id: 'r', children: [section] }
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

  // ADAPTED: 'Expand section' button removed; use body-click (section name) to expand
  it('allows adding and removing list items on a preset list', () => {
    const ops = noopOps()
    render(<SectionView section={presetListSection} isFirst={false} isLast ops={ops} />)
    fireEvent.click(screen.getByText('Experience')) // body-click expands section
    fireEvent.click(screen.getByText('+ Add entry'))
    expect(ops.addItem).toHaveBeenCalledWith('list-exp')
    fireEvent.click(screen.getByLabelText('Remove item'))
    fireEvent.click(screen.getByText('Confirm?'))
    expect(ops.remove).toHaveBeenCalledWith('item-0')
  })

  // ADAPTED: 'Expand section' button removed; use body-click
  it('renders a drag handle per list entry', () => {
    render(<SectionView section={presetListSection} isFirst={false} isLast ops={noopOps()} />)
    fireEvent.click(screen.getByText('Experience'))
    expect(screen.getAllByLabelText('Drag to reorder item')).toHaveLength(1)
  })

  // ADAPTED: 'Expand section'/'Expand item' buttons removed; use body-click and Toggle entry
  it('edits a field value through ops.setValue', () => {
    const ops = noopOps()
    render(<SectionView section={presetListSection} isFirst={false} isLast ops={ops} />)
    fireEvent.click(screen.getByText('Experience')) // expand section
    fireEvent.click(screen.getByLabelText('Toggle entry')) // expand entry
    fireEvent.change(screen.getByDisplayValue('Acme'), { target: { value: 'Acme2' } })
    expect(ops.setValue).toHaveBeenLastCalledWith('i0', 'Acme2')
  })

  // ADAPTED: 'Expand section'/'Expand item' buttons removed; use body-click and Toggle entry.
  // Entry has name='E' so RenameLabel shows 'E'; summary only shows when name is empty.
  it('collapses list entries by default, showing entry name via RenameLabel', () => {
    render(<SectionView section={presetListSection} isFirst={false} isLast ops={noopOps()} />)
    fireEvent.click(screen.getByText('Experience'))
    // entry body (field) hidden; entry name shown via RenameLabel
    expect(screen.queryByDisplayValue('Acme')).toBeNull()
    expect(screen.getByText('E')).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Toggle entry'))
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

  // ADAPTED: ▸/▾ 'Expand section'/'Collapse section' buttons removed; body-click toggles
  it('is collapsed by default and expands/collapses on body-click toggle', () => {
    render(<SectionView section={customSection} isFirst isLast={false} ops={noopOps()} />)
    // collapsed by default: the field value is not rendered
    expect(screen.queryByDisplayValue('Winner')).toBeNull()
    fireEvent.click(screen.getByText('Awards')) // body-click expands
    expect(screen.getByDisplayValue('Winner')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Awards')) // body-click collapses
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

  // ADAPTED: 'Expand section' button removed; use body-click
  it('locks a field from the LLM by default and toggles via the lock control', () => {
    const ops = noopOps()
    render(<SectionView section={customSection} isFirst isLast={false} ops={ops} />)
    fireEvent.click(screen.getByText('Awards')) // expand section
    // locked by default → no instructions box, lock offers to unlock
    expect(screen.queryByLabelText('LLM instructions')).toBeNull()
    fireEvent.click(screen.getByLabelText('Unlock for LLM to write'))
    expect(ops.toggleWritten).toHaveBeenCalledWith('fa')
  })

  // ADAPTED: inline instructions textarea retired → 💬 opens the prompt modal
  it('shows a field prompt control (opening a modal) when a field is LLM-written', () => {
    const written = {
      ...customSection,
      children: [{
        ...customSection.children[0],
        children: [{ ...customSection.children[0].children[0], llm_output: true }],
      }],
    }
    render(<SectionView section={written} isFirst isLast={false} ops={noopOps()} tree={rootOf(written)} />)
    fireEvent.click(screen.getByText('Awards')) // expand section
    expect(screen.queryByLabelText('LLM instructions')).toBeNull() // textarea retired
    expect(screen.getByLabelText('Lock from LLM (keep as typed)')).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Edit field prompt'))
    expect(screen.getByLabelText('Close prompt editor')).toBeInTheDocument() // modal opened
  })
})

describe('SectionView lock + prompt', () => {
  // ADAPTED: 'Expand section' button removed; use body-click
  it('shows a section lock toggle when unlocked (inline prompt retired to modal)', () => {
    const ops = noopOps()
    render(<SectionView section={customSection} isFirst isLast={false} ops={ops} tree={rootOf(customSection)} />)
    fireEvent.click(screen.getByText('Awards'))
    // section unlocked by default → lock offers to lock; inline prompt removed (now in PromptEditorModal)
    expect(screen.getByLabelText('Lock section from LLM')).toBeInTheDocument()
    expect(screen.queryByLabelText('Section prompt')).toBeNull()
  })

  // ADAPTED: 'Expand section' button removed; use body-click
  it('hides the section prompt editor when the section is locked', () => {
    const locked = { ...customSection, locked: true }
    render(<SectionView section={locked} isFirst isLast={false} ops={noopOps()} tree={rootOf(locked)} />)
    fireEvent.click(screen.getByText('Awards'))
    expect(screen.queryByLabelText('Section prompt')).toBeNull()
    expect(screen.getByLabelText('Unlock section for LLM')).toBeInTheDocument()
  })

  it('toggles section lock by id', () => {
    const ops = noopOps()
    render(<SectionView section={customSection} isFirst isLast={false} ops={ops} tree={rootOf(customSection)} />)
    fireEvent.click(screen.getByLabelText('Lock section from LLM'))
    expect(ops.toggleLocked).toHaveBeenCalledWith('sec-c')
  })

  // ADAPTED: 'Expand section'/'Expand item' buttons removed; use body-click and Toggle entry
  it('shows an item lock on a list entry when unlocked (inline prompt retired to modal)', () => {
    const ops = noopOps()
    render(<SectionView section={presetListSection} isFirst={false} isLast ops={ops} tree={rootOf(presetListSection)} />)
    fireEvent.click(screen.getByText('Experience')) // expand section
    fireEvent.click(screen.getByLabelText('Toggle entry')) // expand entry
    expect(screen.getByLabelText('Lock item from LLM')).toBeInTheDocument()
    expect(screen.queryByLabelText('Item prompt')).toBeNull()
  })

  it('shows the section as effectively locked (🔒) when every entry is locked', () => {
    const sec = {
      type: 'section', id: 'exp', name: 'Experience', role: 'experience', visible: true, prompt: '',
      children: [{ type: 'list', id: 'l', name: 'Experience', children: [
        { type: 'group', id: 'e1', name: 'A', visible: true, locked: true, prompt: '', children: [] },
        { type: 'group', id: 'e2', name: 'B', visible: true, locked: true, prompt: '', children: [] },
      ] }],
    }
    render(<SectionView section={sec} isFirst isLast ops={noopOps()} tree={rootOf(sec)} />)
    // section.locked is false, so the toggle's aria stays "Lock…", but its glyph is 🔒
    expect(screen.getByLabelText('Lock section from LLM').textContent).toContain('🔒')
  })
})

// --- New cases from task-7 brief ---

function makeOps() {
  return {
    setValue: vi.fn(), rename: vi.fn(), toggleVisible: vi.fn(), remove: vi.fn(),
    move: vi.fn(), addItem: vi.fn(), addField: vi.fn(), reorder: vi.fn(),
    setInstructions: vi.fn(), toggleWritten: vi.fn(), toggleLocked: vi.fn(),
    setPrompt: vi.fn(),
  }
}

const expSection = {
  type: 'section', id: 's1', name: 'Experience', role: 'experience', visible: true,
  prompt: '', children: [{
    type: 'list', id: 'l1', name: 'Experience', children: [
      { type: 'group', id: 'e1', name: 'RA', visible: true, prompt: '', children: [
        { type: 'field', id: 'f1', name: 'Title', key: 'title', kind: 'text', value: 'RA', visible: true },
      ] },
    ],
  }],
}
const tree = { type: 'root', id: 'r', children: [expSection] }

it('section bar has no up/down or expand-arrow buttons', () => {
  const ops = makeOps()
  render(<SectionView section={expSection} isFirst isLast ops={ops} tree={tree} initialCollapsed={false} />)
  expect(screen.queryByLabelText('Move up')).toBeNull()
  expect(screen.queryByLabelText('Expand section')).toBeNull()
  expect(screen.queryByLabelText('Collapse section')).toBeNull()
})

it('opens the prompt modal from the section message icon', () => {
  const ops = makeOps()
  render(<SectionView section={expSection} isFirst isLast ops={ops} tree={tree} initialCollapsed={false} />)
  fireEvent.click(screen.getByLabelText('Edit section prompt'))
  expect(screen.getByText(/Section prompt — Experience/)).toBeInTheDocument()
})

it('list entry exposes eye and message controls', () => {
  const ops = makeOps()
  render(<SectionView section={expSection} isFirst isLast ops={ops} tree={tree} initialCollapsed={false} />)
  expect(screen.getByLabelText('Edit item prompt')).toBeInTheDocument()
  expect(screen.getByLabelText(/item.*output|Hide item|Show item/i)).toBeInTheDocument()
})

it('preset header section allows adding a field', () => {
  const ops = makeOps()
  const header = {
    type: 'section', id: 'h1', name: 'Header', role: 'header', visible: true, prompt: '',
    children: [{ type: 'group', id: 'g1', name: 'Header', visible: true, children: [
      { type: 'field', id: 'hf1', name: 'Email', key: 'email', kind: 'text', value: '', visible: true },
    ] }],
  }
  const t = { type: 'root', id: 'r', children: [header] }
  render(<SectionView section={header} isFirst isLast ops={ops} tree={t} initialCollapsed={false} />)
  expect(screen.getByText('+ Add field')).toBeInTheDocument()
})
