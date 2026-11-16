import { describe, it, expect, vi, afterEach } from 'vitest'
import { getJobs } from './api'

describe('api 429 handling', () => {
  afterEach(() => { vi.restoreAllMocks() })

  it('dispatches auto-apply:rate-limited with Retry-After and still throws', async () => {
    global.fetch = vi.fn(async () => ({
      ok: false,
      status: 429,
      headers: { get: (h) => (h === 'Retry-After' ? '7' : 'application/json') },
      clone() { return this },
      json: async () => ({ error: 'rate_limited' }),
    }))
    const seen = []
    const handler = (e) => seen.push(e.detail)
    window.addEventListener('auto-apply:rate-limited', handler)
    try {
      await expect(getJobs()).rejects.toMatchObject({ status: 429 })
    } finally {
      window.removeEventListener('auto-apply:rate-limited', handler)
    }
    expect(seen).toEqual([{ retryAfter: 7 }])
  })
})
