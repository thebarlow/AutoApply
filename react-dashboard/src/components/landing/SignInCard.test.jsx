import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import SignInCard from './SignInCard'

describe('SignInCard', () => {
  it('logged out: shows Google + GitHub OAuth links', () => {
    render(<SignInCard isAuthed={false} />)
    expect(screen.getByRole('link', { name: /google/i }).getAttribute('href')).toBe('/auth/login/google')
    expect(screen.getByRole('link', { name: /github/i }).getAttribute('href')).toBe('/auth/login/github')
  })

  it('logged out + betaClosed: shows the sign-in-rejected message', () => {
    render(<SignInCard isAuthed={false} betaClosed />)
    expect(screen.getByText(/couldn't sign you in/i)).toBeTruthy()
    expect(screen.getByText('barlowmatt96@gmail.com')).toBeTruthy()
    expect(screen.queryByText(/closed beta|invite list/i)).toBeNull()
  })

  it('logged out without betaClosed: open-signup copy, no rejection message', () => {
    render(<SignInCard isAuthed={false} />)
    expect(screen.queryByText(/couldn't sign you in/i)).toBeNull()
    expect(screen.getByText(/anyone can sign up/i)).toBeTruthy()
  })

  it('logged in: shows Go to dashboard and no OAuth links', () => {
    render(<SignInCard isAuthed />)
    const cta = screen.getByRole('link', { name: /go to dashboard/i })
    expect(cta.getAttribute('href')).toBe('/')
    expect(screen.queryByRole('link', { name: /google/i })).toBeNull()
    expect(screen.queryByRole('link', { name: /github/i })).toBeNull()
  })
})
