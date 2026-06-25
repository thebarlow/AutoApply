import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import DocumentPreview from './DocumentPreview'

describe('DocumentPreview', () => {
  it('renders an iframe pointed at the versioned PDF endpoint', () => {
    render(<DocumentPreview jobKey="jk" docType="resume" version={3} />)
    const frame = screen.getByTitle('PDF preview')
    expect(frame.tagName).toBe('IFRAME')
    expect(frame.getAttribute('src')).toBe('/api/jobs/jk/resume?v=3')
  })

  it('uses the cover endpoint for cover docs', () => {
    render(<DocumentPreview jobKey="jk" docType="cover" version={1} />)
    expect(screen.getByTitle('PDF preview').getAttribute('src')).toBe('/api/jobs/jk/cover?v=1')
  })

  it('changing version changes the iframe src (forces refetch)', () => {
    const { rerender } = render(<DocumentPreview jobKey="jk" docType="resume" version={1} />)
    expect(screen.getByTitle('PDF preview').getAttribute('src')).toBe('/api/jobs/jk/resume?v=1')
    rerender(<DocumentPreview jobKey="jk" docType="resume" version={2} />)
    expect(screen.getByTitle('PDF preview').getAttribute('src')).toBe('/api/jobs/jk/resume?v=2')
  })

  it('shows a refreshing overlay only while refreshing', () => {
    const { rerender } = render(<DocumentPreview jobKey="jk" docType="resume" version={1} />)
    expect(screen.queryByText('Refreshing…')).toBeNull()
    rerender(<DocumentPreview jobKey="jk" docType="resume" version={1} refreshing />)
    expect(screen.getByText('Refreshing…')).toBeTruthy()
  })
})
