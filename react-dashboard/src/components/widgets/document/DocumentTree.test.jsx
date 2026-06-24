import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import DocumentTree from './DocumentTree'

const doc = {
  type: 'root', id: 'r', children: [
    { type: 'section', id: 's1', name: 'Summary', locked: false, children: [
      { type: 'field', id: 'f1', name: 'Summary', kind: 'text', value: 'Hello' }] },
    { type: 'section', id: 's2', name: 'Skills', locked: true, children: [
      { type: 'group', id: 'g2', name: 'G', children: [
        { type: 'field', id: 'f2', name: 'Skill', kind: 'text', value: 'Python' }] }] },
  ],
}

describe('DocumentTree', () => {
  it('renders section headings and field values', () => {
    render(<DocumentTree doc={doc} onSave={vi.fn()} notes={{}} setNote={vi.fn()} />)
    // "Summary" appears as both section heading and field label
    expect(screen.getAllByText('Summary').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('Skills')).toBeTruthy()
    expect(screen.getByDisplayValue('Hello')).toBeTruthy()
  })

  it('editing a field calls onSave with the updated tree', () => {
    const onSave = vi.fn()
    render(<DocumentTree doc={doc} onSave={onSave} notes={{}} setNote={vi.fn()} />)
    fireEvent.change(screen.getByDisplayValue('Hello'), { target: { value: 'Hi' } })
    const arg = onSave.mock.calls.at(-1)[0]
    expect(arg.children[0].children[0].value).toBe('Hi')
  })

  it('a locked section exposes no feedback control', () => {
    render(<DocumentTree doc={doc} onSave={vi.fn()} notes={{}} setNote={vi.fn()} />)
    // Feedback buttons carry an accessible name starting with "Feedback on".
    // Locked section "Skills" has no feedback buttons at all
    expect(screen.queryByRole('button', { name: /Feedback on Skills/i })).toBeNull()
    // Unlocked section "Summary" has at least one feedback button
    expect(screen.getAllByRole('button', { name: /Feedback on Summary/i }).length).toBeGreaterThanOrEqual(1)
  })
})
