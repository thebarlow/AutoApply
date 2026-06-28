import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi, it, expect } from 'vitest'
import ParsePreview from './ParsePreview'

vi.mock('../../../api', () => ({ draftSectionPrompt: vi.fn().mockResolvedValue({ prompt: 'drafted' }) }))

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
