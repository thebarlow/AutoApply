import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { SectionGallery } from './SectionGallery'

const templates = [
  { id: 'certifications', label: 'Certifications', description: 'Name, issuer, date' },
  { id: 'blank', label: 'Blank section', description: 'Empty custom section' },
]

describe('SectionGallery', () => {
  it('toggles the panel and renders a card per template', () => {
    render(<SectionGallery templates={templates} onAdd={vi.fn()} />)
    // collapsed: only the add button
    expect(screen.queryByText('Certifications')).toBeNull()
    fireEvent.click(screen.getByText('+ Add section'))
    expect(screen.getByText('Certifications')).toBeInTheDocument()
    expect(screen.getByText('Blank section')).toBeInTheDocument()
  })

  it('calls onAdd with the chosen template and collapses', () => {
    const onAdd = vi.fn()
    render(<SectionGallery templates={templates} onAdd={onAdd} />)
    fireEvent.click(screen.getByText('+ Add section'))
    fireEvent.click(screen.getByText('Certifications'))
    expect(onAdd).toHaveBeenCalledWith(templates[0])
    // collapsed again
    expect(screen.queryByText('Blank section')).toBeNull()
  })
})
