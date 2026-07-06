import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Navbar from './components/Navbar'

describe('Navbar About link', () => {
  it('renders an About link to /about', () => {
    render(
      <MemoryRouter>
        <Navbar me={{ email: 'a@b.c' }} />
      </MemoryRouter>
    )
    const link = screen.getByRole('link', { name: /^about$/i })
    expect(link.getAttribute('href')).toBe('/about')
  })
})
