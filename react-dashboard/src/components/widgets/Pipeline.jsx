import { useState, useMemo } from 'react'
import { motion } from 'framer-motion'
import JobCard, { NewIcon, ProcessingIcon } from '../shared/JobCard'

const TABS = ['Inbox', 'Processing', 'Outbound', 'Archives']

const INBOX_STATES = new Set(['new', 'pending_review'])
const OUTBOUND_STATES = new Set(['ready'])
const ARCHIVE_STATES = new Set(['applied', 'contact', 'rejected'])

const ARCHIVE_LABELS = { applied: 'Applied', contact: 'In Contact', rejected: 'Rejected' }
const ARCHIVE_COLORS = { applied: 'text-green-400', contact: 'text-blue-400', rejected: 'text-red-400' }

function statusIconFor(job, processingKeys) {
  if (processingKeys.has(job.job_key)) return <ProcessingIcon />
  if (job.state === 'new') return <NewIcon />
  return null
}

function archiveBadge(state) {
  return (
    <span className={`text-xs font-medium shrink-0 ${ARCHIVE_COLORS[state] ?? 'text-space-dim'}`}>
      {ARCHIVE_LABELS[state] ?? state}
    </span>
  )
}

function JobList({ jobs, processingKeys = new Set(), selectedJob, onJobSelect, showArchiveBadge }) {
  if (jobs.length === 0) {
    return <p className="text-xs text-space-dim py-1">Empty</p>
  }
  return (
    <div className="flex flex-col gap-2">
      {jobs.map((job) => (
        <div key={job.job_key} onClick={() => onJobSelect(job)} className="cursor-pointer">
          <JobCard
            title={job.title || '(no title)'}
            company={job.company || ''}
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

  const tabJobs = useMemo(() => ({
    Inbox: jobs.filter((j) => INBOX_STATES.has(j.state) && !processingKeys.has(j.job_key)),
    Processing: jobs.filter((j) => processingKeys.has(j.job_key)),
    Outbound: jobs.filter((j) => OUTBOUND_STATES.has(j.state)),
    Archives: jobs.filter((j) => ARCHIVE_STATES.has(j.state)),
  }), [jobs, processingKeys])

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
            onClick={() => setActiveTab(tab)}
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

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4">
        <JobList
          jobs={tabJobs[activeTab]}
          processingKeys={processingKeys}
          selectedJob={selectedJob}
          onJobSelect={onJobSelect}
          showArchiveBadge={activeTab === 'Archives'}
        />
      </div>
    </motion.div>
  )
}
