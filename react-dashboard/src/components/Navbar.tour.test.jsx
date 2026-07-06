import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Navbar from './Navbar'

describe('Navbar Take a tour', () => {
  it('dispatches the replay event on click', () => {
    const spy = vi.fn()
    window.addEventListener('auto-apply:tour-replay', spy)
    render(<MemoryRouter><Navbar me={{ email: 'a@b.c' }} /></MemoryRouter>)
    screen.getByRole('button', { name: /take a tour/i }).click()
    expect(spy).toHaveBeenCalled()
    window.removeEventListener('auto-apply:tour-replay', spy)
  })
})
