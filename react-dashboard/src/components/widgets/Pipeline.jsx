import { useState, useMemo } from 'react'
import { motion } from 'framer-motion'
import JobCard, { ProcessingIcon, EyeIcon, WarningIcon } from '../shared/JobCard'

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

export default function Pipeline({ jobs = [], processingKeys = new Set(), selectedJob, onJobSelect }) {
  const [activeTab, setActiveTab] = useState('Inbox')
  const [searchInbox, setSearchInbox] = useState('')
  const [searchArchives, setSearchArchives] = useState('')

  const tabJobs = useMemo(() => ({
    Inbox: jobs.filter((j) => INBOX_STATES.has(j.state)),
    Archives: jobs.filter((j) => ARCHIVE_STATES.has(j.state)),
  }), [jobs])

  const searchQuery = activeTab === 'Inbox' ? searchInbox : searchArchives
  const setSearchQuery = activeTab === 'Inbox' ? setSearchInbox : setSearchArchives

  const visibleJobs = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    if (!q) return tabJobs[activeTab]
    return tabJobs[activeTab].filter((j) =>
      (j.title || '').toLowerCase().includes(q) ||
      (j.company || '').toLowerCase().includes(q)
    )
  }, [tabJobs, activeTab, searchQuery])

  function handleTabChange(tab) {
    setActiveTab(tab)
    setSearchInbox('')
    setSearchArchives('')
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

      {/* Search */}
      <div className="px-4 pt-3 shrink-0">
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
    </motion.div>
  )
}
