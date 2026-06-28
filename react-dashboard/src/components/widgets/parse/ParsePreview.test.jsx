import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi, it, expect } from 'vitest'
import ParsePreview from './ParsePreview'
import { draftSectionPrompt } from '../../../api'

vi.mock('../../../api', () => ({ draftSectionPrompt: vi.fn().mockResolvedValue({ prompt: 'drafted text' }) }))

const proposal = {
  is_onboarding: true,
  builtin: {}, extra_sections: [],
  sections: [
    { name: 'Employment History', origin: 'builtin', builtin_role: 'experience', kind: 'list', customize: true, prompt: 'Tailor.' },
    { name: 'Certifications', origin: 'novel', extra_index: 0, kind: 'list', customize: false, prompt: '' },
  ],
}

it('checking a section reveals its prompt editor', async () => {
  const user = userEvent.setup()
  render(<ParsePreview proposal={proposal} onApply={() => {}} onCancel={() => {}} />)
  // Certifications starts unchecked → no textarea
  const certRow = screen.getByText('Certifications').closest('div')
  const checkbox = certRow.querySelector('input[type=checkbox]')
  expect(certRow.querySelector('textarea')).toBeNull()
  await user.click(checkbox)
  expect(certRow.querySelector('textarea')).not.toBeNull()
})

it('Finish forwards edited sections', async () => {
  const onApply = vi.fn()
  const user = userEvent.setup()
  render(<ParsePreview proposal={proposal} onApply={onApply} onCancel={() => {}} />)
  await user.click(screen.getByRole('button', { name: /finish/i }))
  expect(onApply).toHaveBeenCalledWith(expect.objectContaining({ sections: expect.any(Array) }))
})

it('Draft path: fills purpose+tailoring, calls draftSectionPrompt, and updates textarea', async () => {
  const user = userEvent.setup()
  render(<ParsePreview proposal={proposal} profileId={99} onApply={() => {}} onCancel={() => {}} />)

  // Employment History starts with customize:true, so its textarea is already shown.
  const empRow = screen.getByText('Employment History').closest('div')
  expect(empRow.querySelector('textarea')).not.toBeNull()

  // Open the "Draft from questions" details panel by clicking its summary.
  const summary = empRow.querySelector('summary')
  await user.click(summary)

  // Fill the two question inputs.
  const purposeInput = screen.getByPlaceholderText(/highlight relevant/i)
  const tailoringInput = screen.getByPlaceholderText(/emphasise certs/i)
  await user.type(purposeInput, 'Show career growth')
  await user.type(tailoringInput, 'Match required skills')

  // Click Draft and wait for the API to resolve.
  await user.click(screen.getByRole('button', { name: /^draft$/i }))

  await waitFor(() =>
    expect(draftSectionPrompt).toHaveBeenCalledWith(99, expect.objectContaining({
      section_name: 'Employment History',
      purpose: 'Show career growth',
      tailoring: 'Match required skills',
    }))
  )

  // The textarea should now contain the drafted text.
  await waitFor(() =>
    expect(empRow.querySelector('textarea').value).toBe('drafted text')
  )
})
