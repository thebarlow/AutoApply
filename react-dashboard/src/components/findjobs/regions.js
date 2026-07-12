// Region classification for remote-job "location" strings (e.g. "USA Only",
// "Worldwide", "Europe"). Used by the Find Jobs location dropdown to bucket
// candidates and show per-region counts. Worldwide/anywhere postings count
// toward every region since they're open to applicants everywhere.

const WORLDWIDE = ['worldwide', 'anywhere', 'global']

export const REGIONS = [
  { key: 'Remote', label: 'Remote', terms: ['remote', 'worldwide', 'anywhere', 'global', 'distributed'] },
  { key: 'USA', label: 'USA', terms: ['usa', 'us', 'u.s', 'u.s.a', 'united states', 'america', 'stateside', 'north america'] },
  { key: 'UK', label: 'UK', terms: ['uk', 'u.k', 'united kingdom', 'britain', 'great britain', 'england', 'scotland', 'wales'] },
  { key: 'Europe', label: 'Europe', terms: ['europe', 'european', 'emea', 'eurozone', 'germany', 'france', 'spain', 'netherlands', 'poland', 'portugal', 'ireland', 'italy', 'sweden'] },
  { key: 'Asia', label: 'Asia', terms: ['asia', 'apac', 'india', 'china', 'japan', 'singapore', 'philippines', 'indonesia', 'vietnam', 'malaysia', 'hong kong'] },
  { key: 'Africa', label: 'Africa', terms: ['africa', 'nigeria', 'kenya', 'egypt', 'ghana', 'south africa'] },
  { key: 'Australia', label: 'Australia', terms: ['australia', 'australian', 'oceania', 'new zealand', 'anz', 'sydney', 'melbourne'] },
]

function hasTerm(text, term) {
  const t = term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return new RegExp(`\\b${t}\\b`, 'i').test(text)
}

export function isWorldwide(location) {
  const t = (location || '').toLowerCase()
  return WORLDWIDE.some((w) => t.includes(w))
}

// Region keys a location explicitly names (excludes worldwide handling).
export function regionsFor(location) {
  if (!location) return []
  return REGIONS.filter((r) => r.terms.some((term) => hasTerm(location, term))).map((r) => r.key)
}

export function matchesRegion(location, key) {
  if (key === 'All') return true
  if (isWorldwide(location)) return true
  return regionsFor(location).includes(key)
}

// { All: total, USA: n, UK: n, ... } over a candidate list.
export function regionCounts(candidates) {
  const counts = { All: candidates.length }
  for (const r of REGIONS) counts[r.key] = 0
  for (const c of candidates) {
    if (isWorldwide(c.location)) {
      for (const r of REGIONS) counts[r.key] += 1
      continue
    }
    for (const key of regionsFor(c.location)) counts[key] += 1
  }
  return counts
}
