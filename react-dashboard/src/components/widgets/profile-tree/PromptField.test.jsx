import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { buildChipGroups, ChipTray, PromptField } from './PromptField'

const tree = {
  type: 'root', id: 'r', children: [{
    type: 'section', id: 's', name: 'My Skills', role: null, order: 0, visible: true,
    children: [{ type: 'group', id: 'g', name: 'G', order: 0, visible: true, children: [
      { type: 'field', id: 'f', name: 'Tech', key: 'tech', order: 0, visible: true,
        kind: 'taglist', value: ['Python'] }] }],
  }],
}

describe('buildChipGroups', () => {
  it('has a Job group and a per-section group with field tokens', () => {
    const groups = buildChipGroups(tree)
    const job = groups.find((g) => g.label === 'Job')
    expect(job.chips.some((c) => c.token === '{job.description}')).toBe(true)
    const sec = groups.find((g) => g.label === 'My Skills')
    expect(sec.chips.some((c) => c.token === '{profile.my_skills}')).toBe(true)
    expect(sec.chips.some((c) => c.token === '{profile.my_skills.tech}')).toBe(true)
  })
})

describe('ChipTray', () => {
  it('inserts a chip token on click after expanding its folder', () => {
    const onInsert = vi.fn()
    render(<ChipTray groups={buildChipGroups(tree)} onInsert={onInsert} />)
    fireEvent.click(screen.getByText('Job')) // expand folder
    fireEvent.click(screen.getByText('description'))
    expect(onInsert).toHaveBeenCalledWith('{job.description}')
  })
})

describe('PromptField', () => {
  it('appends an inserted token to the value', () => {
    const onChange = vi.fn()
    render(<PromptField value="hi " onChange={onChange} tree={tree} ariaLabel="Section prompt" />)
    fireEvent.click(screen.getByText('Job'))
    fireEvent.click(screen.getByText('title'))
    expect(onChange).toHaveBeenCalledWith('hi {job.title}')
  })

  it('opens and closes the pop-out editor', () => {
    render(<PromptField value="x" onChange={vi.fn()} tree={tree} ariaLabel="Section prompt" />)
    fireEvent.click(screen.getByLabelText('Expand editor'))
    expect(screen.getByLabelText('Section prompt (expanded)')).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Close editor'))
    expect(screen.queryByLabelText('Section prompt (expanded)')).toBeNull()
  })
})
