import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import LandingPage from './LandingPage'

describe('LandingPage', () => {
  it('logged out: renders all sections and OAuth sign-in', () => {
    render(<LandingPage me={null} />)
    expect(screen.getByRole('heading', { name: /how it works/i })).toBeTruthy()
    expect(screen.getByText(/AI-tailored documents/i)).toBeTruthy()
    expect(screen.getByRole('link', { name: /google/i })).toBeTruthy()
  })

  it('logged out: hero CTA scrolls to the sign-in card', () => {
    const scrollIntoView = vi.fn()
    Element.prototype.scrollIntoView = scrollIntoView
    render(<LandingPage me={null} />)
    screen.getByRole('button', { name: /get started/i }).click()
    expect(scrollIntoView).toHaveBeenCalled()
  })

  it('logged in: shows Go to dashboard, no OAuth links', () => {
    render(<LandingPage me={{ email: 'a@b.c' }} />)
    // both hero CTA and sign-in card link say "go to dashboard"
    expect(screen.getAllByRole('link', { name: /go to dashboard/i }).length).toBeGreaterThan(0)
    expect(screen.queryByRole('link', { name: /google/i })).toBeNull()
  })

  it('passes betaClosed through to the sign-in card', () => {
    render(<LandingPage me={null} betaClosed />)
    expect(screen.getByText(/closed beta/i)).toBeTruthy()
  })
})
