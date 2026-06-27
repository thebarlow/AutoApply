import { render, screen, fireEvent, within } from '@testing-library/react'
import ParsePreview from './ParsePreview'

const proposal = {
  profile_id: 1,
  sections: [
    {
      name: 'Skills',
      origin: 'builtin',
      default_action: 'merge',
      allowed_actions: ['merge', 'replace', 'skip'],
      kind: null,
      preview: null,
    },
    {
      name: 'Certifications',
      origin: 'novel',
      default_action: 'append',
      allowed_actions: ['append', 'skip'],
      kind: 'list',
      preview: 'AWS Certified, GCP Certified',
    },
  ],
}

test('renders Standard sections and Additional sections headings', () => {
  render(
    <ParsePreview
      proposal={proposal}
      onApply={vi.fn()}
      onCancel={vi.fn()}
      applying={false}
    />
  )
  expect(screen.getByText(/Standard sections/i)).toBeInTheDocument()
  expect(screen.getByText(/Additional sections/i)).toBeInTheDocument()
})

test('Apply calls onApply with sections carrying default actions, and Skills select has correct options', () => {
  const onApply = vi.fn()
  render(
    <ParsePreview
      proposal={proposal}
      onApply={onApply}
      onCancel={vi.fn()}
      applying={false}
    />
  )

  // Skills combobox options must equal exactly its allowed_actions
  const skillsRow = screen.getAllByRole('combobox')[0]
  const options = within(skillsRow).getAllByRole('option').map((o) => o.value)
  expect(options).toEqual(['merge', 'replace', 'skip'])

  // Click Apply
  fireEvent.click(screen.getByRole('button', { name: /apply/i }))

  expect(onApply).toHaveBeenCalledTimes(1)
  const arg = onApply.mock.calls[0][0]
  expect(arg.sections[0].action).toBe('merge')
  expect(arg.sections[1].action).toBe('append')
})
