import { describe, it, expect, vi } from 'vitest'
import { render } from '@testing-library/react'
import CreditBalance from '../widgets/CreditBalance'

// Silence the async API calls that happen inside CreditBalance
vi.mock('../../api', () => ({
  getCredits: () => new Promise(() => {}),
  getSystemBalance: () => new Promise(() => {}),
}))

describe('tour targets', () => {
  it('CreditBalance carries data-tour="credit-balance"', () => {
    const { container } = render(<CreditBalance />)
    expect(container.querySelector('[data-tour="credit-balance"]')).not.toBeNull()
  })
})
