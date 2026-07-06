import { describe, it, expect } from 'vitest'
import { PART1_STEPS, PART2_STEPS } from './tourSteps'

describe('tourSteps', () => {
  it('part 1 covers profile arc + inbox + add-job (7 stops)', () => {
    expect(PART1_STEPS).toHaveLength(7)
    const targets = PART1_STEPS.map((s) => s.target)
    expect(targets).toContain('[data-tour="profile-tree"]')
    expect(targets).toContain('[data-tour="add-job"]')
  })

  it('part 2 covers scoring → generate → preview → credits (4 stops)', () => {
    expect(PART2_STEPS).toHaveLength(4)
    const targets = PART2_STEPS.map((s) => s.target)
    expect(targets).toEqual([
      '[data-tour="job-score"]',
      '[data-tour="generate"]',
      '[data-tour="document-preview"]',
      '[data-tour="credit-balance"]',
    ])
  })

  it('every step disables the beacon and has non-empty content', () => {
    for (const s of [...PART1_STEPS, ...PART2_STEPS]) {
      expect(s.disableBeacon).toBe(true)
      expect(typeof s.content).toBe('string')
      expect(s.content.length).toBeGreaterThan(0)
    }
  })
})
