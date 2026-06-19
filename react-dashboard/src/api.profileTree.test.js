import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { getProfileTree, putProfileTree } from './api'

describe('profile tree api', () => {
  beforeEach(() => {
    global.fetch = vi.fn(async () => ({
      ok: true,
      status: 200,
      headers: { get: () => 'application/json' },
      json: async () => ({ tree: { type: 'root', id: 'r', children: [] } }),
    }))
  })
  afterEach(() => { vi.restoreAllMocks() })

  it('getProfileTree GETs the tree route', async () => {
    const out = await getProfileTree(7)
    expect(global.fetch).toHaveBeenCalledWith('/api/config/profiles/7/tree', undefined)
    expect(out.tree.type).toBe('root')
  })

  it('putProfileTree PUTs {tree} as JSON', async () => {
    const tree = { type: 'root', id: 'r', children: [] }
    await putProfileTree(7, tree)
    const [url, opts] = global.fetch.mock.calls[0]
    expect(url).toBe('/api/config/profiles/7/tree')
    expect(opts.method).toBe('PUT')
    expect(JSON.parse(opts.body)).toEqual({ tree })
  })
})
