import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import ResumeCompare from './ResumeCompare'
import * as api from '../../api'

describe('ResumeCompare', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('runs the comparison and shows both columns with scores', async () => {
    vi.spyOn(api, 'resumeCompare').mockResolvedValue({
      model1: { markdown: '## One body', score: 0.7, issues: [] },
      model2: { markdown: '## Two body', score: 0.9, issues: [] },
    })
    render(<ResumeCompare />)
    fireEvent.change(screen.getByLabelText('Job key'), { target: { value: 'job-1' } })
    fireEvent.click(screen.getByText('Compare'))
    await waitFor(() => expect(api.resumeCompare).toHaveBeenCalledWith('job-1'))
    expect(await screen.findByText('One body')).toBeInTheDocument()
    expect(screen.getByText('Two body')).toBeInTheDocument()
    expect(screen.getByText(/0\.7/)).toBeInTheDocument()
    expect(screen.getByText(/0\.9/)).toBeInTheDocument()
  })

  it('shows a model error without crashing the other column', async () => {
    vi.spyOn(api, 'resumeCompare').mockResolvedValue({
      model1: { error: 'boom' },
      model2: { markdown: '## Two body', score: 0.9, issues: [] },
    })
    render(<ResumeCompare />)
    fireEvent.change(screen.getByLabelText('Job key'), { target: { value: 'j' } })
    fireEvent.click(screen.getByText('Compare'))
    expect(await screen.findByText(/boom/)).toBeInTheDocument()
    expect(screen.getByText('Two body')).toBeInTheDocument()
  })
})
