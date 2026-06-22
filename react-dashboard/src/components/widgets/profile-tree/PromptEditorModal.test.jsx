import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { PromptEditorModal } from './PromptEditorModal'

const tree = { type: 'root', id: 'r', children: [] }

it('shows the folded preview for a section node', () => {
  const node = {
    type: 'section', id: 's1', name: 'Experience', prompt: 'Lead with impact',
    children: [{ type: 'list', id: 'l1', children: [
      { type: 'group', id: 'e1', name: 'RA', prompt: 'stress pubs', children: [] },
    ] }],
  }
  render(<PromptEditorModal node={node} isSection tree={tree} onChange={() => {}} onClose={() => {}} />)
  expect(screen.getByText(/\[Experience: Lead with impact \[RA: stress pubs\]\]/)).toBeInTheDocument()
})

it('shows an inert note when the node is locked', () => {
  const node = { type: 'section', id: 's1', name: 'X', prompt: '', locked: true, children: [] }
  render(<PromptEditorModal node={node} isSection tree={tree} onChange={() => {}} onClose={() => {}} />)
  expect(screen.getByText(/inert while .* locked/i)).toBeInTheDocument()
})

it('closes on the close button', () => {
  const onClose = vi.fn()
  const node = { type: 'group', id: 'e1', name: 'RA', prompt: '', children: [] }
  render(<PromptEditorModal node={node} isSection={false} tree={tree} onChange={() => {}} onClose={onClose} />)
  fireEvent.click(screen.getByLabelText('Close prompt editor'))
  expect(onClose).toHaveBeenCalled()
})
