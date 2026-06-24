import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import DocumentModal from './DocumentModal'

vi.mock('../../api', () => ({
  getDocument: vi.fn(),
  putDocument: vi.fn(() => Promise.resolve({})),
  submitFeedback: vi.fn(() => Promise.resolve({})),
}))
import { getDocument } from '../../api'

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
    expect(screen.getByDisplayValue('Hi')).toBeTruthy()
  })

  it('shows a guard for a legacy résumé row (no schema)', async () => {
    getDocument.mockResolvedValue({ profile_summary: 'old', experience: [], projects: [], skills: [] })
    render(<DocumentModal job={job} docType="resume" processing={false} onClose={vi.fn()} />)
    await waitFor(() => expect(screen.getByText(/regenerate/i)).toBeTruthy())
  })
})
