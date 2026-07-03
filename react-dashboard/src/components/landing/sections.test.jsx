import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import Hero from './Hero'
import HowItWorks from './HowItWorks'
import Features from './Features'

describe('Hero', () => {
  it('logged out: CTA reads Get started and fires onCtaClick', () => {
    const onCtaClick = vi.fn()
    render(<Hero isAuthed={false} onCtaClick={onCtaClick} />)
    const btn = screen.getByRole('button', { name: /get started/i })
    btn.click()
    expect(onCtaClick).toHaveBeenCalledTimes(1)
  })

  it('logged in: CTA reads Go to dashboard', () => {
    render(<Hero isAuthed onCtaClick={() => {}} />)
    expect(screen.getByRole('button', { name: /go to dashboard/i })).toBeTruthy()
  })
})

describe('HowItWorks', () => {
  it('renders the three pipeline steps', () => {
    render(<HowItWorks />)
    expect(screen.getByText(/how it works/i)).toBeTruthy()
    expect(screen.getByText(/scrape/i)).toBeTruthy()
    expect(screen.getByText(/tailor/i)).toBeTruthy()
    expect(screen.getByText(/apply/i)).toBeTruthy()
  })
})

describe('Features', () => {
  it('renders four feature cards', () => {
    render(<Features />)
    expect(screen.getByText(/AI-tailored documents/i)).toBeTruthy()
    expect(screen.getByText(/ATS-safe formatting/i)).toBeTruthy()
    expect(screen.getByText(/Job scoring & skill matching/i)).toBeTruthy()
    expect(screen.getByText(/Live PDF preview/i)).toBeTruthy()
  })
})
