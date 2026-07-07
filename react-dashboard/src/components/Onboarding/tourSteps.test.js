import { describe, it, expect } from 'vitest'
import { TOUR_STEPS } from './tourSteps'

describe('tourSteps', () => {
  it('covers the full interactive sequence in order', () => {
    const targets = TOUR_STEPS.map((s) => s.target)
    expect(targets).toEqual([
      '[data-tour="user-name"]',
      '[data-tour="profile-tree"]',
      '[data-tour="profile-section"]',
      '[data-tour="section-lock"]',
      '[data-tour="section-visible"]',
      '[data-tour="section-prompt"]',
      '[data-tour="prompt-modal"]',
      '[data-tour="add-field"]',
      '[data-tour="profile-close"]',
      '[data-tour="job-inbox"]',
      '[data-tour="add-job"]',
      '[data-tour="job-card"]',
      '[data-tour="job-score"]',
      '[data-tour="generate"]',
      '[data-tour="credit-balance"]',
    ])
  })

  it('gated steps hide the footer and name an advance event', () => {
    for (const s of TOUR_STEPS) {
      if (s.advanceOn) {
        expect(s.hideFooter).toBe(true)
        expect(s.spotlightClicks).toBe(true)
      }
    }
    // The action-gated steps: open profile, expand section, open prompt,
    // close prompt, close profile.
    expect(TOUR_STEPS.filter((s) => s.advanceOn).map((s) => s.advanceOn)).toEqual([
      'auto-apply:profile-editor-opened',
      'auto-apply:section-expanded',
      'auto-apply:prompt-editor-opened',
      'auto-apply:prompt-editor-closed',
      'auto-apply:profile-editor-closed',
      'auto-apply:job-opened',
    ])
  })

  it('every step disables the beacon and has non-empty content', () => {
    for (const s of TOUR_STEPS) {
      expect(s.disableBeacon).toBe(true)
      expect(typeof s.content).toBe('string')
      expect(s.content.length).toBeGreaterThan(0)
    }
  })
})
