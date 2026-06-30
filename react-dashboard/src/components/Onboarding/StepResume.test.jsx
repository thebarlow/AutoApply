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
        builtin_role: 'experience',
        kind: 'list',
        customize: true,
        prompt: 'Tailor.',
      },
      {
        name: 'Certifications',
        origin: 'novel',
        extra_index: 0,
        kind: 'list',
        customize: false,
        prompt: '',
      },
    ],
  }),
  applyParse: vi.fn().mockResolvedValue({}),
  draftSectionPrompt: vi.fn().mockResolvedValue({ prompt: 'drafted' }),
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
  const onEdit = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('proposes, applies, then lists the parsed sections', async () => {
    const user = userEvent.setup()
    const { container } = render(<StepResume onFinish={onFinish} onEdit={onEdit} />)

    const file = new File(['resume content'], 'resume.pdf', { type: 'application/pdf' })
    await user.upload(container.querySelector('input[type="file"]'), file)
    await user.click(screen.getByRole('button', { name: /parse with ai/i }))

    await waitFor(() => expect(proposeParse).toHaveBeenCalledWith(1))
    await waitFor(() =>
      expect(applyParse).toHaveBeenCalledWith(1, expect.objectContaining({ sections: expect.any(Array) })),
    )

    // Confirmation message lists the parsed section names.
    expect(await screen.findByText(/parsed the following sections/i)).toBeInTheDocument()
    expect(screen.getByText(/Work Experience, Certifications/)).toBeInTheDocument()
  })

  it('OK calls onFinish; Edit calls onEdit', async () => {
    const user = userEvent.setup()
    const { container } = render(<StepResume onFinish={onFinish} onEdit={onEdit} />)

    const file = new File(['resume content'], 'resume.pdf', { type: 'application/pdf' })
    await user.upload(container.querySelector('input[type="file"]'), file)
    await user.click(screen.getByRole('button', { name: /parse with ai/i }))

    await screen.findByText(/parsed the following sections/i)

    await user.click(screen.getByRole('button', { name: /^edit$/i }))
    expect(onEdit).toHaveBeenCalled()
    expect(onFinish).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: /^ok$/i }))
    expect(onFinish).toHaveBeenCalled()
  })
})
