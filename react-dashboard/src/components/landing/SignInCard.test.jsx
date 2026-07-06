import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import SignInCard from './SignInCard'

describe('SignInCard', () => {
  it('logged out: shows Google + GitHub OAuth links', () => {
    render(<SignInCard isAuthed={false} />)
    expect(screen.getByRole('link', { name: /google/i }).getAttribute('href')).toBe('/auth/login/google')
    expect(screen.getByRole('link', { name: /github/i }).getAttribute('href')).toBe('/auth/login/github')
  })

  it('logged out + betaClosed: shows the closed-beta message', () => {
    render(<SignInCard isAuthed={false} betaClosed />)
    expect(screen.getByText(/closed beta/i)).toBeTruthy()
  })

  it('logged out without betaClosed: no closed-beta message', () => {
    render(<SignInCard isAuthed={false} />)
    expect(screen.queryByText(/closed beta/i)).toBeNull()
  })

  it('logged in: shows Go to dashboard and no OAuth links', () => {
    render(<SignInCard isAuthed />)
    const cta = screen.getByRole('link', { name: /go to dashboard/i })
    expect(cta.getAttribute('href')).toBe('/')
    expect(screen.queryByRole('link', { name: /google/i })).toBeNull()
    expect(screen.queryByRole('link', { name: /github/i })).toBeNull()
  })
})
