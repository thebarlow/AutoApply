import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import DocumentModal from './DocumentModal'

vi.mock('../../api', () => ({
  getDocument: vi.fn(),
  putDocument: vi.fn(() => Promise.resolve({})),
  submitFeedback: vi.fn(() => Promise.resolve({})),
}))
import { getDocument, putDocument } from '../../api'

const job = { job_key: 'jk', title: 'Dev' }

describe('DocumentModal schema branch', () => {
  beforeEach(() => vi.clearAllMocks())

  it('renders DocumentTree for a tree-v1 résumé', async () => {
    getDocument.mockResolvedValue({
      schema: 'tree-v1', type: 'root', id: 'r', children: [
        { type: 'section', id: 's1', name: 'Summary', locked: false, children: [
          { type: 'field', id: 'f1', name: 'Summary', kind: 'text', value: 'Hi' }] }],
    })
    render(<DocumentModal job={job} docType="resume" processing={false} onClose={vi.fn()} />)
    await waitFor(() => expect(screen.getAllByText('Summary').length).toBeGreaterThan(0))
    fireEvent.click(screen.getByText('Summary'))
    expect(screen.getByDisplayValue('Hi')).toBeTruthy()
  })

  it('shows a guard for a legacy résumé row (no schema)', async () => {
    getDocument.mockResolvedValue({ profile_summary: 'old', experience: [], projects: [], skills: [] })
    render(<DocumentModal job={job} docType="resume" processing={false} onClose={vi.fn()} />)
    await waitFor(() => expect(screen.getByText(/regenerate/i)).toBeTruthy())
  })

  it('renders a PDF preview iframe beside a tree-v1 résumé', async () => {
    getDocument.mockResolvedValue({
      schema: 'tree-v1', type: 'root', id: 'r', children: [
        { type: 'section', id: 's1', name: 'Summary', locked: false, children: [
          { type: 'field', id: 'f1', name: 'Summary', kind: 'text', value: 'Hi' }] }],
    })
    render(<DocumentModal job={job} docType="resume" processing={false} onClose={vi.fn()} />)
    const frame = await screen.findByTitle('PDF preview')
    expect(frame.getAttribute('src')).toBe('/api/jobs/jk/resume?v=1')
  })

  it('renders a PDF preview iframe for a cover letter', async () => {
    getDocument.mockResolvedValue({ body: 'Dear team', section_order: [] })
    render(<DocumentModal job={job} docType="cover" processing={false} onClose={vi.fn()} />)
    const frame = await screen.findByTitle('PDF preview')
    expect(frame.getAttribute('src')).toBe('/api/jobs/jk/cover?v=1')
  })

  it('shows a placeholder instead of an iframe when there is no document', async () => {
    getDocument.mockRejectedValue(new Error('GET /api/jobs/jk/resume/document → 404'))
    render(<DocumentModal job={job} docType="resume" processing={false} onClose={vi.fn()} />)
    await waitFor(() => expect(screen.getByText(/Generate this document to see a preview/i)).toBeTruthy())
    expect(screen.queryByTitle('PDF preview')).toBeNull()
  })

  it('bumps the preview version after a successful tree save', async () => {
    getDocument.mockResolvedValue({
      schema: 'tree-v1', type: 'root', id: 'r', children: [
        { type: 'section', id: 's1', name: 'Summary', locked: false, children: [
          { type: 'field', id: 'f1', name: 'Summary', kind: 'text', value: 'Hi' }] }],
    })
    render(<DocumentModal job={job} docType="resume" processing={false} onClose={vi.fn()} />)
    const frame = await screen.findByTitle('PDF preview')
    expect(frame.getAttribute('src')).toBe('/api/jobs/jk/resume?v=1')
    fireEvent.click(screen.getByText('Summary'))            // expand the section
    const input = screen.getByDisplayValue('Hi')
    fireEvent.change(input, { target: { value: 'Hello' } }) // edits trigger handleTreeSave (PUT)
    await waitFor(() =>
      expect(screen.getByTitle('PDF preview').getAttribute('src')).toBe('/api/jobs/jk/resume?v=2'))
  })
})
