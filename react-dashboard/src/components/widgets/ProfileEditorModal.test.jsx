import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import ProfileEditorModal from './ProfileEditorModal'

describe('ProfileEditorModal', () => {
  it('renders children and closes on the close button and backdrop', () => {
    const onClose = vi.fn()
    render(<ProfileEditorModal onClose={onClose}><p>inside</p></ProfileEditorModal>)
    expect(screen.getByText('inside')).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Close profile editor'))
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
