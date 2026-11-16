import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import Privacy from './Privacy'
import Terms from './Terms'
import SiteFooter from './SiteFooter'

describe('Privacy', () => {
  it('renders the policy with key sections and the contact email', () => {
    render(<Privacy />)
    expect(screen.getByRole('heading', { level: 1, name: /privacy policy/i })).toBeTruthy()
    expect(screen.getByText(/effective 16 november 2026/i)).toBeTruthy()
    expect(screen.getByRole('heading', { name: /ai processing/i })).toBeTruthy()
    expect(screen.getByRole('heading', { name: /cookies and tracking/i })).toBeTruthy()
    expect(screen.getByRole('heading', { name: /deleting or exporting/i })).toBeTruthy()
    expect(screen.getAllByText('barlowmatt96@gmail.com').length).toBeGreaterThan(0)
  })
})

describe('Terms', () => {
  it('renders the terms with key sections', () => {
    render(<Terms />)
    expect(screen.getByRole('heading', { level: 1, name: /terms of service/i })).toBeTruthy()
    expect(screen.getByRole('heading', { name: /ai-generated documents are drafts/i })).toBeTruthy()
    expect(screen.getByRole('heading', { name: /credits and payments/i })).toBeTruthy()
    expect(screen.getByRole('heading', { name: /using your own api key/i })).toBeTruthy()
  })
})

describe('SiteFooter', () => {
  it('links to the privacy policy and terms', () => {
    render(<SiteFooter />)
    expect(screen.getByRole('link', { name: /privacy policy/i }).getAttribute('href')).toBe('/privacy')
    expect(screen.getByRole('link', { name: /terms of service/i }).getAttribute('href')).toBe('/terms')
  })
})
