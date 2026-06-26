import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { ResumeTheme } from './ProfileDetail'

vi.mock('../../api', () => ({
  getThemes: () => Promise.resolve([
    { id: 'classic', label: 'Classic' },
    { id: 'modern', label: 'Modern' },
    { id: 'compact', label: 'Compact' },
  ]),
}))

describe('ResumeTheme', () => {
  it('renders options from getThemes and shows the stored value', async () => {
    render(<ResumeTheme value="modern" onSave={() => {}} />)
    await waitFor(() => expect(screen.getByLabelText(/theme/i)).toBeInTheDocument())
    expect(screen.getByLabelText(/theme/i).value).toBe('modern')
    expect(screen.getByRole('option', { name: 'Compact' })).toBeInTheDocument()
  })

  it('persists the selected theme', async () => {
    const onSave = vi.fn()
    render(<ResumeTheme value="classic" onSave={onSave} />)
    await waitFor(() => screen.getByLabelText(/theme/i))
    fireEvent.change(screen.getByLabelText(/theme/i), { target: { value: 'compact' } })
    expect(onSave).toHaveBeenCalledWith({ resume_theme: 'compact' })
  })
})
