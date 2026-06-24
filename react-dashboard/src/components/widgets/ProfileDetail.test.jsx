import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

vi.mock('../../api', () => ({
  getProfile: vi.fn(), updateProfile: vi.fn(), resetProfile: vi.fn(),
  getPrompt: vi.fn(), putPrompt: vi.fn(), resetPrompt: vi.fn(),
}))
import { ResumePageLimit } from './ProfileDetail'

// AccordionSection defaults to collapsed; open the "document" section for tests
beforeEach(() => {
  sessionStorage.setItem('profile-accordion:document', '1')
})
afterEach(() => {
  sessionStorage.clear()
})

describe('ResumePageLimit', () => {
  it('initializes on with the stored integer', () => {
    render(<ResumePageLimit value={2} onSave={vi.fn()} />)
    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByLabelText('Max pages')).toHaveValue('2')
  })

  it('initializes off (unlimited) when value is absent', () => {
    render(<ResumePageLimit value={undefined} onSave={vi.fn()} />)
    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'false')
    expect(screen.getByLabelText('Max pages')).toBeDisabled()
  })

  it('toggling off persists null', () => {
    const onSave = vi.fn()
    render(<ResumePageLimit value={2} onSave={onSave} />)
    fireEvent.click(screen.getByRole('switch'))
    expect(onSave).toHaveBeenCalledWith({ resume_max_pages: null })
  })

  it('changing the page count persists the integer when on', () => {
    const onSave = vi.fn()
    render(<ResumePageLimit value={1} onSave={onSave} />)
    fireEvent.change(screen.getByLabelText('Max pages'), { target: { value: '3' } })
    expect(onSave).toHaveBeenCalledWith({ resume_max_pages: 3 })
  })

  it('rejects non-digits in the page input', () => {
    const onSave = vi.fn()
    render(<ResumePageLimit value={1} onSave={onSave} />)
    fireEvent.change(screen.getByLabelText('Max pages'), { target: { value: 'a' } })
    // non-digit stripped → empty input, no positive integer → falls back to 1
    expect(onSave).toHaveBeenCalledWith({ resume_max_pages: 1 })
  })
})
