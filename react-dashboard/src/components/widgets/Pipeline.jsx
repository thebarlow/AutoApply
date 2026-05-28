import { useState, useMemo } from 'react'
import { motion } from 'framer-motion'
import JobCard, { ProcessingIcon, EyeIcon, WarningIcon } from '../shared/JobCard'
import { uploadJob } from '../../api'

const TABS = ['Inbox', 'Archives']

const INBOX_STATES = new Set(['new', 'pending_review'])
const ARCHIVE_STATES = new Set(['applied', 'contact', 'rejected', 'deleted'])

const ARCHIVE_LABELS = { applied: 'Applied', contact: 'In Contact', rejected: 'Rejected', deleted: 'Deleted' }
const ARCHIVE_COLORS = { applied: 'text-green-400', contact: 'text-blue-400', rejected: 'text-red-400', deleted: 'text-space-dim' }

function statusIconFor(job, processingKeys) {
  if (processingKeys.has(job.job_key)) return <ProcessingIcon />
  if (job.unread_indicator === 'error') return <WarningIcon />
  if (job.unread_indicator === 'ok') return <EyeIcon />
  return null
}

function archiveBadge(state) {
  return (
    <span className={`text-xs font-medium shrink-0 ${ARCHIVE_COLORS[state] ?? 'text-space-dim'}`}>
      {ARCHIVE_LABELS[state] ?? state}
    </span>
  )
}

function InboxEmpty() {
  return (
    <div className="text-center py-12 text-space-dim">
      <p className="mb-2">No jobs to see here!</p>
      <a
        href="/docs"
        className="text-purple-400 hover:underline"
      >
        How to upload jobs →
      </a>
    </div>
  )
}

function ArchiveEmpty() {
  return (
    <div className="text-center py-12 text-space-dim">
      <p className="mb-1">No archived jobs yet.</p>
      <p className="text-xs">Jobs you mark applied, irrelevant, or delete will appear here.</p>
    </div>
  )
}

function JobList({ jobs, processingKeys = new Set(), selectedJob, onJobSelect, showArchiveBadge, activeTab }) {
  if (jobs.length === 0) {
    return activeTab === 'Archives' ? <ArchiveEmpty /> : <InboxEmpty />
  }
  return (
    <div className="flex flex-col gap-2">
      {jobs.map((job) => (
        <div key={job.job_key} onClick={() => onJobSelect(job)} className="cursor-pointer">
          <JobCard
            title={job.title || '(no title)'}
            company={job.company || ''}
            state={job.state}
            score={job.final_score ?? null}
            appliedAt={job.applied_at || null}
            scrapedAt={job.scraped_at || null}
            salaryMin={job.ext_salary_min ?? null}
            salaryMax={job.ext_salary_max ?? null}
            salaryRaw={job.salary || null}
            flagged={job.flagged ?? false}
            docs={{
              resume: !!(job.resume_path || job.resume_md_exists),
              coverLetter: !!(job.cover_path || job.cover_md_exists),
            }}
            statusIcon={
              showArchiveBadge
                ? archiveBadge(job.state)
                : statusIconFor(job, processingKeys)
            }
            selected={selectedJob?.job_key === job.job_key}
          />
        </div>
      ))}
    </div>
  )
}

const SORT_OPTIONS = ['Date', 'Score', 'Salary']

function parseSalaryForSort(job) {
  if (job.ext_salary_min != null) return job.ext_salary_min
  if (!job.salary) return null
  const nums = job.salary.replace(/,/g, '').match(/\d+(?:\.\d+)?[kK]?/g)
  if (!nums || nums.length === 0) return null
  const toNum = (s) => parseFloat(s) * (/[kK]$/i.test(s) ? 1000 : 1)
  const values = nums.map(toNum).filter(n => n > 0)
  return values.length > 0 ? Math.min(...values) : null
}

function UploadModal({ onClose, onSubmit }) {
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [company, setCompany] = useState('')
  const [location, setLocation] = useState('')
  const [salary, setSalary] = useState('')
  const [url, setUrl] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  const canSubmit = title.trim() && description.trim() && !submitting

  const handleSubmit = async () => {
    if (!canSubmit) return
    setSubmitting(true)
    setError(null)
    try {
      const result = await onSubmit({
        title: title.trim(),
        description: description.trim(),
        company: company.trim(),
        location: location.trim(),
        salary: salary.trim(),
        url: url.trim(),
      })
      if (result?.status === 'duplicate') {
        setError('This job already exists (duplicate URL)')
        setSubmitting(false)
        return
      }
      onClose()
    } catch (e) {
      setError(e?.message || 'Upload failed')
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-[#0f0f1a] border border-space-border rounded-xl w-[90%] max-w-md p-5 flex flex-col gap-3 shadow-2xl max-h-[90vh] overflow-y-auto">
        <p className="text-sm font-semibold text-space-text">Upload a job</p>

        <label className="text-xs text-space-dim">Title <span className="text-red-400">*</span></label>
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          className="w-full bg-white/5 border border-space-border rounded-lg px-3 py-2 text-sm text-space-text focus:outline-none focus:border-purple-500"
        />

        <label className="text-xs text-space-dim">Description <span className="text-red-400">*</span></label>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={6}
          className="w-full bg-white/5 border border-space-border rounded-lg px-3 py-2 text-sm text-space-text focus:outline-none focus:border-purple-500"
        />

        <label className="text-xs text-space-dim">Company</label>
        <input
          value={company}
          onChange={(e) => setCompany(e.target.value)}
          className="w-full bg-white/5 border border-space-border rounded-lg px-3 py-2 text-sm text-space-text focus:outline-none focus:border-purple-500"
        />

        <label className="text-xs text-space-dim">Location</label>
        <input
          value={location}
          onChange={(e) => setLocation(e.target.value)}
          className="w-full bg-white/5 border border-space-border rounded-lg px-3 py-2 text-sm text-space-text focus:outline-none focus:border-purple-500"
        />

        <label className="text-xs text-space-dim">Salary</label>
        <input
          value={salary}
          onChange={(e) => setSalary(e.target.value)}
          className="w-full bg-white/5 border border-space-border rounded-lg px-3 py-2 text-sm text-space-text focus:outline-none focus:border-purple-500"
        />

        <label className="text-xs text-space-dim">Job URL</label>
        <input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://…"
          className="w-full bg-white/5 border border-space-border rounded-lg px-3 py-2 text-sm text-space-text focus:outline-none focus:border-purple-500"
        />

        {error && <p className="text-xs text-red-400">{error}</p>}

        <div className="flex gap-2 mt-2">
          <button
            onClick={handleSubmit}
            disabled={!canSubmit}
            className="flex-1 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white text-sm font-semibold"
          >
            {submitting ? 'Uploading…' : 'Upload'}
          </button>
          <button
            onClick={onClose}
            disabled={submitting}
            className="px-4 py-2 rounded-lg border border-space-border text-sm text-space-dim hover:text-space-text"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  )
}

export default function Pipeline({ jobs = [], processingKeys = new Set(), selectedJob, onJobSelect }) {
  const [activeTab, setActiveTab] = useState('Inbox')
  const [searchInbox, setSearchInbox] = useState('')
  const [searchArchives, setSearchArchives] = useState('')
  const [sortBy, setSortBy] = useState('Date')
  const [sortDir, setSortDir] = useState('desc')
  const [showUpload, setShowUpload] = useState(false)

  const tabJobs = useMemo(() => ({
    Inbox: jobs.filter((j) => INBOX_STATES.has(j.state)),
    Archives: jobs.filter((j) => ARCHIVE_STATES.has(j.state)),
  }), [jobs])

  const sortedJobs = useMemo(() => {
    const list = [...(tabJobs[activeTab] || [])]
    const dir = sortDir === 'desc' ? 1 : -1
    if (sortBy === 'Score') {
      return list.sort((a, b) => {
        if (a.final_score == null && b.final_score == null) return 0
        if (a.final_score == null) return 1
        if (b.final_score == null) return -1
        return dir * (b.final_score - a.final_score)
      })
    }
    if (sortBy === 'Date') {
      return list.sort((a, b) => {
        const da = a.applied_at || a.scraped_at || ''
        const db_ = b.applied_at || b.scraped_at || ''
        if (!da && !db_) return 0
        if (!da) return 1
        if (!db_) return -1
        return dir * (da < db_ ? 1 : da > db_ ? -1 : 0)
      })
    }
    if (sortBy === 'Salary') {
      return list.sort((a, b) => {
        const sa = parseSalaryForSort(a)
        const sb = parseSalaryForSort(b)
        if (sa == null && sb == null) return 0
        if (sa == null) return 1
        if (sb == null) return -1
        return dir * (sb - sa)
      })
    }
    return list
  }, [tabJobs, activeTab, sortBy, sortDir])

  const searchQuery = activeTab === 'Inbox' ? searchInbox : searchArchives
  const setSearchQuery = activeTab === 'Inbox' ? setSearchInbox : setSearchArchives

  const visibleJobs = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    if (!q) return sortedJobs
    return sortedJobs.filter((j) =>
      (j.title || '').toLowerCase().includes(q) ||
      (j.company || '').toLowerCase().includes(q)
    )
  }, [sortedJobs, searchQuery])

  function handleTabChange(tab) {
    setActiveTab(tab)
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: 'easeOut' }}
      whileHover={{ boxShadow: '0 0 24px 2px rgba(109,40,217,0.15)' }}
      className="bg-white/5 border border-space-border rounded-xl flex flex-col overflow-hidden h-full"
    >
      {/* Tab bar */}
      <div className="flex border-b border-space-border shrink-0">
        {TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => handleTabChange(tab)}
            className={`flex-1 py-2.5 text-xs font-semibold uppercase tracking-widest transition-colors
              ${activeTab === tab
                ? 'text-purple-400 border-b-2 border-purple-400 bg-white/5'
                : 'text-space-dim hover:text-space-text'
              }`}
          >
            {tab}
            {tabJobs[tab].length > 0 && (
              <span className="ml-1 text-[10px] opacity-50">({tabJobs[tab].length})</span>
            )}
          </button>
        ))}
      </div>

      {/* Sort + Upload */}
      <div className="flex items-center gap-3 px-4 pt-3 shrink-0">
        {SORT_OPTIONS.map((opt) => (
          <button
            key={opt}
            onClick={() => setSortBy(opt)}
            className={`text-xs font-medium pb-0.5 transition-colors
              ${sortBy === opt
                ? 'text-purple-400 border-b border-purple-400'
                : 'text-space-dim hover:text-space-text'
              }`}
          >
            {opt}
          </button>
        ))}
        <button
          onClick={() => setSortDir(d => d === 'desc' ? 'asc' : 'desc')}
          className="ml-auto text-space-dim hover:text-space-text transition-colors"
          title={sortDir === 'desc' ? 'Descending' : 'Ascending'}
        >
          {sortDir === 'desc'
            ? <span style={{ fontSize: '10px', lineHeight: 1 }}>▼</span>
            : <span style={{ fontSize: '10px', lineHeight: 1 }}>▲</span>
          }
        </button>
        {activeTab === 'Inbox' && (
          <button
            onClick={() => setShowUpload(true)}
            className="text-xs font-medium text-purple-400 hover:text-purple-300 border border-purple-500/40 rounded px-2 py-0.5"
          >
            + Upload
          </button>
        )}
      </div>

      {/* Search */}
      <div className="px-4 pt-2 shrink-0">
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Search jobs…"
          className="w-full bg-white/5 border border-white/10 rounded-md px-3 py-1.5 text-xs text-space-text placeholder-space-dim outline-none focus:border-purple-500/50 transition-colors"
        />
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4">
        <JobList
          jobs={visibleJobs}
          processingKeys={processingKeys}
          selectedJob={selectedJob}
          onJobSelect={onJobSelect}
          showArchiveBadge={activeTab === 'Archives'}
          activeTab={activeTab}
        />
      </div>
      {showUpload && (
        <UploadModal
          onClose={() => setShowUpload(false)}
          onSubmit={async (fields) => uploadJob(fields)}
        />
      )}
    </motion.div>
  )
}
