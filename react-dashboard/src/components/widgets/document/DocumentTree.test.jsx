import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import DocumentTree from './DocumentTree'

const doc = {
  type: 'root', id: 'r', children: [
    { type: 'section', id: 's1', name: 'Summary', locked: false, children: [
      { type: 'field', id: 'f1', name: 'Summary', kind: 'text', value: 'Hello' }] },
    { type: 'section', id: 's2', name: 'Experience', locked: false, children: [
      { type: 'list', id: 'l2', name: 'Experience', children: [
        { type: 'group', id: 'g1', name: 'Acme', locked: false, children: [
          { type: 'field', id: 'c1', name: 'Company', kind: 'text', value: 'Acme' },
          { type: 'field', id: 't1', name: 'Title', kind: 'text', value: 'Engineer' }] }] }] },
    { type: 'section', id: 's3', name: 'Certs', locked: true, children: [
      { type: 'group', id: 'g3', name: 'C', children: [
        { type: 'field', id: 'f3', name: 'Cert', kind: 'text', value: 'AWS' }] }] },
  ],
}

const noop = () => {}

describe('DocumentTree', () => {
  it('renders section headings but keeps fields hidden until expanded', () => {
    render(<DocumentTree doc={doc} onSave={vi.fn()} notes={{}} setNote={vi.fn()} />)
    expect(screen.getByText('Summary')).toBeTruthy()
    expect(screen.getByText('Experience')).toBeTruthy()
    expect(screen.queryByDisplayValue('Hello')).toBeNull()
  })

  it('expanding a section reveals an editable field that saves the updated tree', () => {
    const onSave = vi.fn()
    render(<DocumentTree doc={doc} onSave={onSave} notes={{}} setNote={vi.fn()} />)
    fireEvent.click(screen.getByText('Summary'))
    fireEvent.change(screen.getByDisplayValue('Hello'), { target: { value: 'Hi' } })
    expect(onSave.mock.calls.at(-1)[0].children[0].children[0].value).toBe('Hi')
  })

  it('a multi-entry section renders a collapsed sub-card per entry', () => {
    render(<DocumentTree doc={doc} onSave={vi.fn()} notes={{}} setNote={vi.fn()} />)
    fireEvent.click(screen.getByText('Experience'))
    expect(screen.getByText('Acme')).toBeTruthy()            // entry summary label
    expect(screen.queryByDisplayValue('Engineer')).toBeNull() // entry collapsed
    fireEvent.click(screen.getByText('Acme'))
    expect(screen.getByDisplayValue('Engineer')).toBeTruthy()
  })

  it('a locked section renders read-only fields and no feedback control', () => {
    render(<DocumentTree doc={doc} onSave={vi.fn()} notes={{}} setNote={vi.fn()} />)
    expect(screen.queryByRole('button', { name: /Feedback on Certs/i })).toBeNull()
    fireEvent.click(screen.getByText('Certs'))
    expect(screen.getByDisplayValue('AWS')).toBeDisabled()
  })

  it('collects feedback at section and entry level only (no per-field control)', () => {
    render(<DocumentTree doc={doc} onSave={vi.fn()} notes={{}} setNote={vi.fn()} />)
    expect(screen.getByRole('button', { name: /Feedback on Summary/i })).toBeTruthy()
    expect(screen.getByRole('button', { name: /Feedback on Experience/i })).toBeTruthy()
    fireEvent.click(screen.getByText('Experience'))
    expect(screen.getByRole('button', { name: /Feedback on Acme/i })).toBeTruthy()
    expect(screen.queryByRole('button', { name: /Feedback on Company/i })).toBeNull()
  })

  it('section feedback records a note keyed by the section id', () => {
    const setNote = vi.fn()
    render(<DocumentTree doc={doc} onSave={vi.fn()} notes={{}} setNote={setNote} />)
    fireEvent.click(screen.getByRole('button', { name: /Feedback on Summary/i }))
    fireEvent.change(screen.getByPlaceholderText(/change in this section/i), { target: { value: 'punchier' } })
    expect(setNote).toHaveBeenCalledWith('s1', { section: 'Summary', label: 'Summary', note: 'punchier' })
  })
})
