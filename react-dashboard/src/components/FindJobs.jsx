import { useEffect, useState, useCallback } from 'react'
import JobCard from './shared/JobCard'
import Navbar from './Navbar'
import { effectiveStatus } from './findjobs/borderStatus'
import { searchJobs, scrapeSelected, getLastSearch, getMe } from '../api'

export default function FindJobs() {
  const [me, setMe] = useState(null)
  const [query, setQuery] = useState('')
  const [candidates, setCandidates] = useState([])
  const [selected, setSelected] = useState(() => new Set())
  const [viewed, setViewed] = useState(() => new Set())
  const [detail, setDetail] = useState(null)  // candidate shown in preview
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    getMe().then(setMe)
  }, [])

  const runSearch = useCallback(async (q) => {
    if (!q || !q.trim()) return
    setLoading(true)
    try {
      const data = await searchJobs(q)
      setCandidates(data.candidates || [])
      setSelected(new Set())
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    getLastSearch().then(({ query: q }) => {
      if (q) { setQuery(q); runSearch(q) }
    })
  }, [runSearch])

  function toggle(key) {
    setSelected((prev) => {
      const next = new Set(prev)
      next.has(key) ? next.delete(key) : next.add(key)
      return next
    })
  }

  function openDetail(cand) {
    setDetail(cand)
    setViewed((prev) => new Set(prev).add(cand.job_key))
  }

  async function doScrape() {
    const payloads = candidates.filter((c) => selected.has(c.job_key))
    if (payloads.length === 0) return
    await scrapeSelected(payloads)
    const scrapedKeys = new Set(payloads.map((c) => c.job_key))
    setCandidates((prev) =>
      prev.map((c) => (scrapedKeys.has(c.job_key) ? { ...c, status: 'scraped' } : c)))
    setSelected(new Set())
  }

  return (
    <>
      <Navbar me={me} />
      <div className="flex flex-col h-[calc(100vh-53px)]">
      <div className="sticky top-0 z-10 flex gap-2 p-4 bg-space-bg border-b border-space-border">
        <input
          className="flex-1 rounded-md bg-white/5 border border-white/10 px-3 py-2 text-sm text-space-text"
          placeholder="Search remote jobs…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && runSearch(query)}
        />
        <button
          onClick={() => runSearch(query)}
          className="rounded-md bg-purple-600 hover:bg-purple-500 px-4 py-2 text-sm font-semibold text-white"
        >Search</button>
        <button
          onClick={() => runSearch(query)}
          aria-label="Refresh"
          className="rounded-md bg-white/5 hover:bg-white/10 px-3 py-2 text-sm text-space-dim"
        >↻</button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-2">
        {loading && <p className="text-sm text-space-dim">Searching…</p>}
        {!loading && candidates.length === 0 && (
          <p className="text-sm text-space-dim">Enter a search to find jobs.</p>
        )}
        {candidates.map((c) => (
          <div key={c.job_key} onClick={() => openDetail(c)} className="cursor-pointer">
            <JobCard
              title={c.title}
              company={c.company}
              selected={selected.has(c.job_key)}
              borderStatus={effectiveStatus(c.status, viewed.has(c.job_key))}
              leading={
                <input
                  type="checkbox"
                  className="mt-1 mr-2 self-start"
                  checked={selected.has(c.job_key)}
                  onClick={(e) => e.stopPropagation()}
                  onChange={() => toggle(c.job_key)}
                />
              }
            />
          </div>
        ))}
      </div>

      {detail && (
        <div className="border-t border-space-border p-4 max-h-64 overflow-y-auto">
          <div className="flex justify-between items-center mb-2">
            <h3 className="text-sm font-semibold text-space-text">{detail.title} — {detail.company}</h3>
            <button onClick={() => setDetail(null)} className="text-space-dim text-sm">✕</button>
          </div>
          <p className="text-xs text-space-dim whitespace-pre-wrap">{detail.description}</p>
        </div>
      )}

      <div className="sticky bottom-0 flex justify-end gap-3 p-4 bg-space-bg border-t border-space-border">
        <button
          onClick={doScrape}
          disabled={selected.size === 0}
          className="rounded-md bg-purple-600 hover:bg-purple-500 disabled:opacity-40 px-5 py-2 text-sm font-semibold text-white"
        >Scrape ({selected.size})</button>
      </div>
      </div>
    </>
  )
}
