import { useEffect, useState, useCallback, useRef, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import DOMPurify from 'dompurify'
import JobCard, { relativeAge } from './shared/JobCard'
import Navbar from './Navbar'
import { effectiveStatus } from './findjobs/borderStatus'
import { REGIONS, matchesRegion, regionCounts } from './findjobs/regions'
import { searchJobs, scrapeSelected, getLastSearch, getMe } from '../api'

const DELETED_KEY = 'findjobs:deletedIds'

// Strip presentational markup from third-party descriptions so pasted
// screenshots / inline colors can't fight the dark theme (white boxes,
// unreadable black text). Our own .job-preview CSS then owns all styling.
const SANITIZE_OPTS = {
  FORBID_TAGS: ['style', 'font', 'img', 'figure', 'svg'],
  FORBID_ATTR: ['style', 'bgcolor', 'color', 'align', 'width', 'height', 'face'],
}

function loadDeleted() {
  try {
    return new Set(JSON.parse(localStorage.getItem(DELETED_KEY) || '[]'))
  } catch {
    return new Set()
  }
}

function persistDeleted(set) {
  try {
    localStorage.setItem(DELETED_KEY, JSON.stringify([...set]))
  } catch {
    /* cache is best-effort; ignore quota/availability errors */
  }
}

function parseExclude(text) {
  return text.split(',').map((w) => w.trim()).filter(Boolean)
}

export default function FindJobs() {
  const [me, setMe] = useState(null)
  const [query, setQuery] = useState('')
  const [excludeText, setExcludeText] = useState('')
  const [region, setRegion] = useState('All')
  const [candidates, setCandidates] = useState([])
  const [viewed, setViewed] = useState(() => new Set())
  const [detail, setDetail] = useState(null)  // user's explicit preview pick
  const [loading, setLoading] = useState(false)
  const [hasSearched, setHasSearched] = useState(false)
  const [busy, setBusy] = useState(() => new Set())  // candidate_ids mid-scrape
  const [error, setError] = useState(null)

  // Deleted-job ids live in a client cache; filtered out of every search.
  const deletedRef = useRef(loadDeleted())

  // Region counts span the whole snapshot; the list is filtered to the pick.
  const counts = useMemo(() => regionCounts(candidates), [candidates])
  const visible = useMemo(
    () => candidates.filter((c) => matchesRegion(c.location, region)),
    [candidates, region])
  // Preview the explicit pick when it's still visible, else the first card.
  const shown = (detail && visible.some((c) => c.candidate_id === detail.candidate_id))
    ? detail : (visible[0] || null)

  useEffect(() => {
    getMe().then(setMe)
  }, [])

  const runSearch = useCallback(async (q, exclude = []) => {
    if (!q || !q.trim()) return
    setLoading(true)
    setError(null)
    setHasSearched(true)
    // Overwrite the previous list immediately so stale results never linger.
    setCandidates([])
    setDetail(null)
    try {
      const data = await searchJobs(q, exclude)
      const list = (data.candidates || []).filter(
        (c) => !deletedRef.current.has(c.candidate_id))
      setCandidates(list)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    getLastSearch().then(({ query: q, exclude = [] }) => {
      if (q) {
        setQuery(q)
        setExcludeText(exclude.join(', '))
        runSearch(q, exclude)
      }
    })
  }, [runSearch])

  function submit() {
    runSearch(query, parseExclude(excludeText))
  }

  function openDetail(cand) {
    setDetail(cand)
    setViewed((prev) => new Set(prev).add(cand.candidate_id))
  }

  function removeCandidate(id) {
    setCandidates((prev) => prev.filter((c) => c.candidate_id !== id))
  }

  async function scrapeOne(cand) {
    setBusy((prev) => new Set(prev).add(cand.candidate_id))
    setError(null)
    try {
      await scrapeSelected([cand])
      // staged or duplicate — either way it now lives in the inbox, so drop it.
      removeCandidate(cand.candidate_id)
    } catch {
      setError('Scrape failed. Please try again.')
    } finally {
      setBusy((prev) => {
        const next = new Set(prev)
        next.delete(cand.candidate_id)
        return next
      })
    }
  }

  function deleteOne(cand) {
    deletedRef.current.add(cand.candidate_id)
    persistDeleted(deletedRef.current)
    removeCandidate(cand.candidate_id)
  }

  function actions(cand, size = 'sm') {
    const disabled = busy.has(cand.candidate_id)
    const pad = size === 'lg' ? 'w-9 h-9 text-lg' : 'w-7 h-7 text-sm'
    return (
      <div className="flex items-center gap-2">
        <button
          aria-label="Scrape job"
          title="Scrape into inbox"
          disabled={disabled}
          onClick={(e) => { e.stopPropagation(); scrapeOne(cand) }}
          className={`${pad} grid place-items-center rounded-md bg-emerald-600/80 hover:bg-emerald-500 disabled:opacity-40 text-white`}
        >✓</button>
        <button
          aria-label="Delete job"
          title="Remove from results"
          disabled={disabled}
          onClick={(e) => { e.stopPropagation(); deleteOne(cand) }}
          className={`${pad} grid place-items-center rounded-md bg-white/5 hover:bg-red-500/80 hover:text-white text-space-dim`}
        >✕</button>
      </div>
    )
  }

  const inputCls = 'rounded-md bg-white/5 border border-white/10 px-3 py-2 text-sm text-space-text'

  return (
    <>
      <Navbar me={me} />
      <div className="flex flex-col h-[calc(100vh-53px)]">
      <div className="sticky top-0 z-10 flex flex-wrap gap-2 p-4 bg-space-bg border-b border-space-border">
        <input
          className={`flex-1 min-w-[200px] ${inputCls}`}
          placeholder="Search remote jobs…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && submit()}
        />
        <input
          className={`w-48 ${inputCls}`}
          placeholder="Exclude words (e.g. senior)"
          value={excludeText}
          onChange={(e) => setExcludeText(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && submit()}
        />
        <select
          aria-label="Filter by location"
          className={inputCls}
          value={region}
          onChange={(e) => setRegion(e.target.value)}
        >
          {/* Native option popups render on a white background, so force dark
              option text for legibility (light theme text would be invisible). */}
          <option className="text-black" value="All">All locations ({counts.All ?? 0})</option>
          {REGIONS.map((r) => (
            <option className="text-black" key={r.key} value={r.key}>{r.label} ({counts[r.key] ?? 0})</option>
          ))}
        </select>
        <button
          onClick={submit}
          className="rounded-md bg-purple-600 hover:bg-purple-500 px-4 py-2 text-sm font-semibold text-white"
        >Search</button>
        <button
          onClick={submit}
          aria-label="Refresh"
          className="rounded-md bg-white/5 hover:bg-white/10 px-3 py-2 text-sm text-space-dim"
        >↻</button>
      </div>

      {error && (
        <p className="px-4 py-2 text-sm text-red-400 border-b border-space-border">{error}</p>
      )}

      {hasSearched && !loading && (
        <p className="px-4 py-2 text-xs text-space-dim border-b border-space-border">
          Showing {visible.length} of {candidates.length} live
          {' '}{candidates.length === 1 ? 'listing' : 'listings'} from Remotive &amp; RemoteOK
          {region !== 'All' ? ` in ${region}` : ''} — a snapshot of what those boards have posted
          right now, not the full market. Check back as new roles are posted.
        </p>
      )}

      <div className="flex-1 flex overflow-hidden">
        {/* Left column: job cards */}
        <div className="w-2/5 min-w-[300px] overflow-y-auto p-4 space-y-2 border-r border-space-border">
          {loading && <p className="text-sm text-space-dim">Searching…</p>}
          {!loading && visible.length === 0 && (
            <p className="text-sm text-space-dim">
              {candidates.length === 0 ? 'Enter a search to find jobs.' : 'No jobs in this location.'}
            </p>
          )}
          <AnimatePresence initial={false}>
            {visible.map((c) => (
              <motion.div
                key={c.candidate_id}
                layout
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, x: 40, height: 0, marginTop: 0, transition: { duration: 0.2 } }}
                onClick={() => openDetail(c)}
                className="cursor-pointer"
              >
                <JobCard
                  title={c.title}
                  company={c.company}
                  location={c.location}
                  postedAt={c.posted_at}
                  salaryRaw={c.salary}
                  salaryMin={c.salary_min}
                  salaryMax={c.salary_max}
                  selected={detail?.candidate_id === c.candidate_id}
                  borderStatus={effectiveStatus(c.status, viewed.has(c.candidate_id))}
                  trailing={actions(c, 'sm')}
                />
              </motion.div>
            ))}
          </AnimatePresence>
        </div>

        {/* Right column: preview */}
        <div className="flex-1 overflow-y-auto p-6">
          {shown ? (
            <>
              <div className="mb-4 flex items-start justify-between gap-4">
                <div>
                  <h3 className="text-lg font-semibold text-space-text">{shown.title}</h3>
                  <p className="text-sm text-space-dim">{shown.company}</p>
                  {shown.location && (
                    <p className="text-xs text-space-dim">📍 {shown.location}</p>
                  )}
                  {shown.posted_at && (
                    <p className="text-xs text-space-dim">Posted {relativeAge(shown.posted_at)}</p>
                  )}
                  {shown.url && (
                    <a
                      href={shown.url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-xs text-purple-400 hover:text-purple-300"
                    >View original posting ↗</a>
                  )}
                </div>
                {actions(shown, 'lg')}
              </div>
              <div
                className="job-preview text-sm text-space-text max-w-none"
                dangerouslySetInnerHTML={{
                  __html: DOMPurify.sanitize(shown.description || '', SANITIZE_OPTS),
                }}
              />
            </>
          ) : (
            <p className="text-sm text-space-dim">Select a job to preview it.</p>
          )}
        </div>
      </div>
      </div>
    </>
  )
}
