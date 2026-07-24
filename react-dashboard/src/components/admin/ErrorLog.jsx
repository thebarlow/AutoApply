import { useState, useEffect, useCallback, Fragment } from 'react'
import { getErrors, getErrorDetail, clearErrors } from '../../api'

export default function ErrorLog() {
  const [rows, setRows] = useState([])
  const [filters, setFilters] = useState({ level: '', route: '', profile_id: '', since: '' })
  const [detail, setDetail] = useState(null)
  const [expandedId, setExpandedId] = useState(null)

  const load = useCallback(() => {
    getErrors(filters).then((d) => setRows(d?.errors || [])).catch(() => setRows([]))
  }, [filters])

  useEffect(() => { load() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const expand = async (id) => {
    if (expandedId === id) {
      setExpandedId(null)
      setDetail(null)
      return
    }
    setExpandedId(id)
    setDetail(null)
    try {
      const d = await getErrorDetail(id)
      setDetail(d)
    } catch {
      setDetail(null)
    }
  }

  const onClear = async () => {
    await clearErrors()
    setExpandedId(null)
    setDetail(null)
    load()
  }

  return (
    <div className="flex flex-col gap-6">
      <section>
        <h2 className="text-lg font-semibold mb-3">Error Log</h2>
        <div className="flex flex-wrap gap-2 items-end mb-3">
          <input
            type="text"
            value={filters.level}
            onChange={(e) => setFilters({ ...filters, level: e.target.value })}
            placeholder="level"
            className="px-3 py-2 rounded-lg bg-white/5 border border-space-border text-sm focus:outline-none focus:border-purple-500"
          />
          <input
            type="text"
            value={filters.route}
            onChange={(e) => setFilters({ ...filters, route: e.target.value })}
            placeholder="route"
            className="px-3 py-2 rounded-lg bg-white/5 border border-space-border text-sm focus:outline-none focus:border-purple-500"
          />
          <input
            type="text"
            value={filters.profile_id}
            onChange={(e) => setFilters({ ...filters, profile_id: e.target.value })}
            placeholder="profile id"
            className="px-3 py-2 rounded-lg bg-white/5 border border-space-border text-sm focus:outline-none focus:border-purple-500"
          />
          <input
            type="text"
            value={filters.since}
            onChange={(e) => setFilters({ ...filters, since: e.target.value })}
            placeholder="since (ISO)"
            className="px-3 py-2 rounded-lg bg-white/5 border border-space-border text-sm focus:outline-none focus:border-purple-500"
          />
          <button
            type="button"
            onClick={load}
            className="px-3 py-2 rounded-lg bg-purple-600 text-white text-sm font-semibold hover:bg-purple-500"
          >
            Apply
          </button>
          <button
            type="button"
            onClick={onClear}
            className="ml-auto px-3 py-2 rounded-lg bg-red-600 text-white text-sm font-semibold hover:bg-red-500"
          >
            Clear all
          </button>
        </div>

        <div className="border border-space-border rounded-lg overflow-hidden">
          <div className="grid grid-cols-[1fr_auto_1fr_auto_1fr_2fr_auto] gap-2 px-3 py-2 text-xs uppercase tracking-widest text-space-dim bg-white/5">
            <span>Last seen</span><span>Level</span><span>Route</span><span>Method</span><span>Profile</span><span>Message</span><span>×</span>
          </div>
          <div className="max-h-96 overflow-y-auto">
            {rows.map((r) => (
              <Fragment key={r.id}>
                <div
                  className="grid grid-cols-[1fr_auto_1fr_auto_1fr_2fr_auto] gap-2 px-3 py-2 text-sm items-center border-t border-space-border/50 cursor-pointer hover:bg-white/5"
                  onClick={() => expand(r.id)}
                >
                  <span className="text-space-dim">{r.last_seen}</span>
                  <span>{r.level}</span>
                  <span className="truncate" title={r.route}>{r.route}</span>
                  <span>{r.method || '—'}</span>
                  <span className="text-space-dim">{r.account_email ? `${r.account_email} (#${r.profile_id})` : (r.profile_id ?? '—')}</span>
                  <span className="truncate" title={r.message}>{r.message}</span>
                  <span>×{r.count}</span>
                </div>
                {expandedId === r.id && (
                  <div className="border-t border-space-border/50 px-3 py-2 bg-black/20">
                    {detail === null ? (
                      <p className="text-xs text-space-dim">Loading…</p>
                    ) : (
                      <pre className="text-xs overflow-x-auto whitespace-pre-wrap text-space-dim">
                        {detail.traceback || '(no traceback)'}
                        {`\nrequest_id: ${detail.request_id ?? '—'}`}
                      </pre>
                    )}
                  </div>
                )}
              </Fragment>
            ))}
            {rows.length === 0 && <p className="px-3 py-3 text-xs text-space-dim">No errors recorded.</p>}
          </div>
        </div>
      </section>
    </div>
  )
}
