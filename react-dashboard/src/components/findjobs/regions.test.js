import { describe, it, expect } from 'vitest'
import { matchesRegion, regionsFor, isWorldwide, regionCounts } from './regions'

describe('region classification', () => {
  it('maps common location strings to regions', () => {
    expect(regionsFor('USA Only')).toEqual(['USA'])
    expect(regionsFor('United Kingdom')).toEqual(['UK'])
    expect(regionsFor('Europe')).toEqual(['Europe'])
  })

  it('does not misclassify Ukraine as UK (word boundary)', () => {
    expect(regionsFor('Ukraine')).not.toContain('UK')
  })

  it('treats worldwide/anywhere as every region', () => {
    expect(isWorldwide('Worldwide')).toBe(true)
    expect(matchesRegion('Anywhere', 'USA')).toBe(true)
    expect(matchesRegion('Anywhere', 'Asia')).toBe(true)
  })

  it('All matches everything', () => {
    expect(matchesRegion('', 'All')).toBe(true)
    expect(matchesRegion('Mars', 'All')).toBe(true)
  })

  it('counts worldwide toward all regions plus a total', () => {
    const counts = regionCounts([
      { location: 'USA Only' },
      { location: 'Worldwide' },
      { location: 'Europe' },
    ])
    expect(counts.All).toBe(3)
    expect(counts.USA).toBe(2)      // USA Only + Worldwide
    expect(counts.Europe).toBe(2)   // Europe + Worldwide
    expect(counts.Asia).toBe(1)     // Worldwide only
  })
})
