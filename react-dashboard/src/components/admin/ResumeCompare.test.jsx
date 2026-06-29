import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import ResumeCompare from './ResumeCompare'
import * as api from '../../api'

const CSS = '.resume { color: #111; }'

describe('ResumeCompare', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('aligns sections in rows with scores in the header', async () => {
    vi.spyOn(api, 'resumeCompare').mockResolvedValue({
      css: CSS,
      model1: {
        markdown: 'x', score: 0.7, issues: [],
        sections: [
          { heading: 'Profile', html: '<h2>Profile</h2><p>one profile</p>' },
          { heading: 'Skills', html: '<h2>Skills</h2><p>one skills</p>' },
        ],
      },
      model2: {
        markdown: 'y', score: 0.9, issues: [],
        sections: [
          { heading: 'Profile', html: '<h2>Profile</h2><p>two profile</p>' },
        ],
      },
    })
    render(<ResumeCompare />)
    fireEvent.change(screen.getByLabelText('Job key'), { target: { value: 'job-1' } })
    fireEvent.click(screen.getByText('Compare'))
    await waitFor(() => expect(api.resumeCompare).toHaveBeenCalledWith('job-1'))

    // Heading labels (rendered as row labels, not inside iframes) — union, model1 order first.
    expect(await screen.findByText('Profile')).toBeInTheDocument()
    expect(screen.getByText('Skills')).toBeInTheDocument()
    // Scores in header row.
    expect(screen.getByText(/0\.7/)).toBeInTheDocument()
    expect(screen.getByText(/0\.9/)).toBeInTheDocument()
    // Model 2 lacks Skills → a "not present" placeholder appears.
    expect(screen.getByText(/not present/i)).toBeInTheDocument()
    // Cells are iframes carrying the section html via srcDoc.
    const frames = document.querySelectorAll('iframe')
    expect(frames.length).toBe(3) // 2 model1 + 1 model2
    expect(frames[0].getAttribute('srcdoc')).toContain('one profile')
    expect(frames[0].getAttribute('srcdoc')).toContain(CSS)
  })

  it('shows a model error without crashing the other column', async () => {
    vi.spyOn(api, 'resumeCompare').mockResolvedValue({
      css: CSS,
      model1: { error: 'boom' },
      model2: {
        markdown: 'y', score: 0.9, issues: [],
        sections: [{ heading: 'Profile', html: '<h2>Profile</h2><p>ok</p>' }],
      },
    })
    render(<ResumeCompare />)
    fireEvent.change(screen.getByLabelText('Job key'), { target: { value: 'j' } })
    fireEvent.click(screen.getByText('Compare'))
    expect(await screen.findByText(/boom/)).toBeInTheDocument()
    // Healthy model still renders its section iframe.
    const frames = document.querySelectorAll('iframe')
    expect(frames.length).toBe(1)
    expect(frames[0].getAttribute('srcdoc')).toContain('ok')
  })
})
