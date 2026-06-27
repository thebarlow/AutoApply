import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import StepResume from './StepResume'

// Mock GatedButton to a plain button so credits context is not needed.
vi.mock('../shared/GatedButton', () => ({
  default: ({ children, onClick, disabled }) => (
    <button onClick={onClick} disabled={disabled}>{children}</button>
  ),
}))

vi.mock('../shared/Spinner', () => ({ default: () => <span>…</span> }))

vi.mock('../../api', () => ({
  uploadProfileResume: vi.fn().mockResolvedValue({ path: '/tmp/r.pdf', filename: 'r.pdf' }),
  getProfiles: vi.fn().mockResolvedValue({ active_id: 1, profiles: [{ id: 1 }] }),
  setActiveProfile: vi.fn().mockResolvedValue({}),
  getProfile: vi.fn().mockResolvedValue({ name: 'P', data: {} }),
  updateProfile: vi.fn().mockResolvedValue({}),
  proposeParse: vi.fn().mockResolvedValue({
    sections: [
      {
        name: 'Work Experience',
        origin: 'builtin',
        kind: 'list',
        allowed_actions: ['merge', 'skip'],
        default_action: 'merge',
      },
      {
        name: 'Certifications',
        origin: 'novel',
        kind: 'list',
        allowed_actions: ['add', 'skip'],
        default_action: 'add',
        preview: 'AWS Certified',
      },
    ],
  }),
  applyParse: vi.fn().mockResolvedValue({}),
}))

import {
  uploadProfileResume,
  getProfiles,
  setActiveProfile,
  getProfile,
  updateProfile,
  proposeParse,
  applyParse,
} from '../../api'

describe('StepResume', () => {
  const onFinish = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('calls proposeParse after upload and shows ParsePreview', async () => {
    const user = userEvent.setup()
    const { container } = render(<StepResume onFinish={onFinish} />)

    const file = new File(['resume content'], 'resume.pdf', { type: 'application/pdf' })
    const input = container.querySelector('input[type="file"]')
    await user.upload(input, file)

    await user.click(screen.getByRole('button', { name: /parse with ai/i }))

    // proposeParse called with profileId=1
    await waitFor(() => expect(proposeParse).toHaveBeenCalledWith(1))

    // ParsePreview heading visible
    expect(await screen.findByText(/review parsed sections/i)).toBeInTheDocument()
    // Standard sections heading
    expect(screen.getByText(/standard sections/i)).toBeInTheDocument()
    // Novel sections heading
    expect(screen.getByText(/additional sections found/i)).toBeInTheDocument()
  })

  it('calls applyParse and onFinish when Apply is clicked', async () => {
    const user = userEvent.setup()
    const { container } = render(<StepResume onFinish={onFinish} />)

    const file = new File(['resume content'], 'resume.pdf', { type: 'application/pdf' })
    await user.upload(container.querySelector('input[type="file"]'), file)
    await user.click(screen.getByRole('button', { name: /parse with ai/i }))

    // Wait for preview to appear
    await screen.findByText(/review parsed sections/i)

    await user.click(screen.getByRole('button', { name: /apply/i }))

    await waitFor(() => expect(applyParse).toHaveBeenCalledWith(1, expect.objectContaining({ sections: expect.any(Array) })))
    await waitFor(() => expect(onFinish).toHaveBeenCalled())
  })

  it('returns to uploader when Cancel is clicked', async () => {
    const user = userEvent.setup()
    const { container } = render(<StepResume onFinish={onFinish} />)

    const file = new File(['resume content'], 'resume.pdf', { type: 'application/pdf' })
    await user.upload(container.querySelector('input[type="file"]'), file)
    await user.click(screen.getByRole('button', { name: /parse with ai/i }))

    await screen.findByText(/review parsed sections/i)

    await user.click(screen.getByRole('button', { name: /cancel/i }))

    expect(screen.getByText(/upload your resume/i)).toBeInTheDocument()
    expect(onFinish).not.toHaveBeenCalled()
  })
})
