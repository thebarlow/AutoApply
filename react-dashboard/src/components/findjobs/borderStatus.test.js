import { describe, it, expect } from 'vitest'
import { effectiveStatus, BORDER_CLASS } from './borderStatus'

describe('effectiveStatus precedence', () => {
  it('applied beats viewed', () => {
    expect(effectiveStatus('applied', true)).toBe('applied')
  })
  it('scraped beats viewed', () => {
    expect(effectiveStatus('scraped', true)).toBe('scraped')
  })
  it('viewed beats none', () => {
    expect(effectiveStatus('none', true)).toBe('viewed')
  })
  it('none when nothing set', () => {
    expect(effectiveStatus('none', false)).toBe('none')
  })
  it('every status has a border class', () => {
    for (const s of ['applied', 'scraped', 'viewed', 'none']) {
      expect(BORDER_CLASS[s]).toBeTruthy()
    }
  })
})
