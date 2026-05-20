import { useState, useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { getProfiles, createProfile, getProviders, saveProvider } from '../../api'

// ─── Icons ────────────────────────────────────────────────────────────────────

function BackArrow() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10 12L6 8l4-4" />
    </svg>
  )
}

// ─── Shared ───────────────────────────────────────────────────────────────────

const inputClass =
  'w-full bg-white/5 border border-space-border rounded-lg px-3 py-2 text-sm text-space-text placeholder-space-dim focus:outline-none focus:border-purple-500 transition-colors'

const slideVariants = {
  enter: { x: 40, opacity: 0 },
  center: { x: 0, opacity: 1 },
  exit: { x: -40, opacity: 0 },
}

// ─── Preview tab ──────────────────────────────────────────────────────────────

const STATE_LABELS = { new: 'New', pending_review: 'Pending Review', ready: 'Ready', applied: 'Applied', contact: 'In Contact', rejected: 'Rejected' }

function ExtractionView({ data }) {
  const fields = [
    { key: 'seniority', label: 'Seniority' },
    { key: 'role_type', label: 'Role Type' },
    { key: 'domain', label: 'Domain' },
    { key: 'work_arrangement', label: 'Work Arrangement' },
    { key: 'employment_type', label: 'Employment Type' },
    { key: 'required_skills', label: 'Required Skills' },
    { key: 'preferred_skills', label: 'Preferred Skills' },
    { key: 'tech_stack', label: 'Tech Stack' },
    { key: 'key_responsibilities', label: 'Responsibilities' },
    { key: 'company_signals', label: 'Company Signals' },
  ]
  return (
    <div className="flex flex-col gap-3">
      {fields.map(({ key, label }) => {
        const val = data[key]
        if (!val || (Array.isArray(val) && val.length === 0)) return null
        return (
          <div key={key}>
            <p className="text-xs font-semibold text-space-dim mb-1">{label}</p>
            {Array.isArray(val)
              ? <ul className="list-disc list-inside text-xs space-y-0.5 text-space-text">{val.map((v, i) => <li key={i}>{v}</li>)}</ul>
              : <p className="text-xs text-space-text">{val}</p>
            }
          </div>
        )
      })}
    </div>
  )
}

function PreviewTab({ job }) {
  const [view, setView] = useState('raw')

  // Reset view when a different job is selected
  useEffect(() => { setView('raw') }, [job?.job_key])

  if (!job) return null

  const score = job.final_score != null ? Math.round(job.final_score * 100) + '%' : '—'
  const stateLabel = STATE_LABELS[job.state] ?? job.state

  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <div>
        <h2 className="text-base font-semibold text-space-text leading-tight">{job.title || '(no title)'}</h2>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1.5">
          {job.company && <span className="text-xs text-space-dim">{job.company}</span>}
          {job.location && <span className="text-xs text-space-dim">{job.location}</span>}
          {job.salary && <span className="text-xs text-space-dim">{job.salary}</span>}
          <span className="text-xs font-semibold text-purple-400">{score}</span>
          <span className="text-xs text-space-dim">{stateLabel}</span>
        </div>
      </div>

      <hr className="border-space-border" />

      {/* Toggle */}
      <div className="flex gap-2">
        {['raw', 'extracted'].map((v) => (
          <button
            key={v}
            onClick={() => setView(v)}
            disabled={v === 'extracted' && !job.extraction_json_exists}
            className={`px-3 py-1 rounded text-xs font-semibold capitalize transition-colors
              ${view === v ? 'bg-purple-600 text-white' : 'text-space-dim hover:text-space-text border border-space-border'}
              disabled:opacity-30 disabled:cursor-not-allowed`}
          >
            {v}
          </button>
        ))}
      </div>

      {/* Description */}
      <div>
        {view === 'raw' && (
          <p className="text-xs text-space-dim leading-relaxed whitespace-pre-wrap">
            {job.description || 'No description available.'}
          </p>
        )}
        {view === 'extracted' && (
          job.extraction
            ? <ExtractionView data={job.extraction} />
            : <p className="text-xs text-space-dim">No extraction yet.</p>
        )}
      </div>
    </div>
  )
}

// ─── Tasks tab ────────────────────────────────────────────────────────────────

function TasksTab({ jobs, processingKeys }) {
  const processing = jobs.filter((j) => processingKeys.has(j.job_key))
  if (processing.length === 0) {
    return <p className="text-sm text-space-dim">No active tasks.</p>
  }
  return (
    <div className="flex flex-col gap-2">
      {processing.map((job) => (
        <div key={job.job_key} className="flex items-center gap-2 rounded-lg px-3 py-2 bg-white/[0.03] border border-white/5">
          <svg className="shrink-0 animate-spin text-purple-400" width="14" height="14" viewBox="0 0 14 14" fill="currentColor">
            <circle cx="7" cy="7" r="6" fill="none" stroke="currentColor" strokeWidth="2" strokeDasharray="20 18" />
          </svg>
          <div className="min-w-0">
            <p className="text-sm text-space-text truncate">{job.title || '(no title)'}</p>
            <p className="text-xs text-space-dim">{job.company || ''}</p>
          </div>
        </div>
      ))}
    </div>
  )
}

// ─── User tab ─────────────────────────────────────────────────────────────────

function CreateProfile({ onBack, onCreated }) {
  const [name, setName] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const handleSave = async () => {
    const trimmed = name.trim()
    if (!trimmed) { setError('Name is required'); return }
    setSaving(true)
    try {
      const profile = await createProfile(trimmed)
      onCreated(profile)
    } catch {
      setError('Failed to create profile')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <label className="text-xs text-space-dim">Profile Name</label>
        <input
          className={inputClass}
          value={name}
          onChange={(e) => { setName(e.target.value); setError(null) }}
          placeholder="e.g. Software Engineer"
        />
        {error && <p className="text-xs text-red-400">{error}</p>}
      </div>
      <div className="flex gap-2">
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex-1 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white text-sm font-semibold transition-colors"
        >
          {saving ? 'Saving…' : 'Save Profile'}
        </button>
        <button onClick={onBack} className="px-4 py-2 rounded-lg border border-space-border text-sm text-space-dim hover:text-space-text transition-colors">
          Cancel
        </button>
      </div>
    </div>
  )
}

function ProfileList({ onCreateProfile }) {
  const [profiles, setProfiles] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    getProfiles()
      .then((data) => setProfiles(data.profiles ?? []))
      .catch(() => setError('Failed to load profiles'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <p className="text-xs text-space-dim">Loading…</p>
  if (error) return <p className="text-xs text-red-400">{error}</p>

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        {profiles.length === 0 && (
          <p className="text-xs text-space-dim">No profiles yet.</p>
        )}
        {profiles.map((profile) => (
          <div
            key={profile.id}
            className="flex items-center gap-3 rounded-lg px-3 py-2.5 bg-white/[0.03] border border-white/5"
          >
            <p className="text-sm font-medium text-space-text">{profile.name || 'Unnamed'}</p>
          </div>
        ))}
      </div>
      <button
        onClick={onCreateProfile}
        className="w-full py-2 rounded-lg border border-space-border hover:border-purple-500/50 text-sm text-space-dim hover:text-space-text transition-colors"
      >
        + Create Profile
      </button>
    </div>
  )
}

function UserTab({ onProfileSettings }) {
  return (
    <div className="flex flex-col gap-4">
      <button
        onClick={onProfileSettings}
        className="w-full py-2 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-sm font-semibold transition-colors"
      >
        Profile Settings
      </button>
    </div>
  )
}

// ─── Advanced tab ─────────────────────────────────────────────────────────────

function AdvancedTab() {
  const [providers, setProviders] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState(null)
  const timerRef = useRef(null)

  useEffect(() => {
    getProviders()
      .then((data) => setProviders(data.providers ?? []))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => () => clearTimeout(timerRef.current), [])

  const handleSave = async (provider, field, value) => {
    setSaving(true)
    try {
      await saveProvider(provider.id, { ...provider, [field]: value })
      setProviders((prev) =>
        prev.map((p) => p.id === provider.id ? { ...p, [field]: value } : p)
      )
      setStatus('Saved ✓')
    } catch {
      setStatus('Save failed')
    } finally {
      setSaving(false)
      clearTimeout(timerRef.current)
      timerRef.current = setTimeout(() => setStatus(null), 2500)
    }
  }

  if (loading) return <p className="text-xs text-space-dim">Loading…</p>
  if (providers.length === 0) return <p className="text-xs text-space-dim">No providers configured.</p>

  return (
    <div className="flex flex-col gap-6">
      {providers.map((provider) => (
        <div key={provider.id} className="flex flex-col gap-3">
          <p className="text-xs font-semibold uppercase tracking-widest text-space-dim">{provider.name}</p>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-space-dim">Default Model</label>
            <input
              className={inputClass}
              value={provider.default_model || ''}
              onChange={(e) => setProviders((prev) =>
                prev.map((p) => p.id === provider.id ? { ...p, default_model: e.target.value } : p)
              )}
              onBlur={(e) => {
                if (e.target.value !== (provider.default_model || '')) {
                  handleSave(provider, 'default_model', e.target.value)
                }
              }}
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-space-dim">API Key</label>
            <input
              type="password"
              className={inputClass}
              placeholder="Enter new key to replace existing"
              onBlur={(e) => { if (e.target.value) handleSave(provider, 'api_key', e.target.value) }}
            />
          </div>
        </div>
      ))}
      {status && <p className={`text-xs ${status.includes('failed') ? 'text-red-400' : 'text-green-400'}`}>{status}</p>}
    </div>
  )
}

// ─── Root ─────────────────────────────────────────────────────────────────────

const TABS = ['User', 'Tasks', 'Advanced', 'Preview']

export default function Settings({ selectedJob, activeTab, onTabChange, jobs, processingKeys }) {
  const [view, setView] = useState('main') // 'main' | 'profiles' | 'createProfile'

  const isPreviewDisabled = selectedJob === null

  const handleTabClick = (tab) => {
    if (tab === 'Preview' && isPreviewDisabled) return
    onTabChange(tab)
    setView('main')
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: 'easeOut' }}
      whileHover={{ boxShadow: '0 0 24px 2px rgba(109,40,217,0.15)' }}
      className="bg-white/5 border border-space-border rounded-xl flex flex-col overflow-hidden h-full"
    >
      {/* Header */}
      {view === 'main' ? (
        <div className="flex border-b border-space-border shrink-0">
          {TABS.map((tab) => {
            const disabled = tab === 'Preview' && isPreviewDisabled
            return (
              <button
                key={tab}
                onClick={() => handleTabClick(tab)}
                disabled={disabled}
                className={`flex-1 py-2.5 text-xs font-semibold uppercase tracking-widest transition-colors
                  ${activeTab === tab && !disabled
                    ? 'text-purple-400 border-b-2 border-purple-400 bg-white/5'
                    : disabled
                    ? 'text-space-dim/30 cursor-not-allowed'
                    : 'text-space-dim hover:text-space-text'
                  }`}
              >
                {tab}
              </button>
            )
          })}
        </div>
      ) : (
        <div className="flex items-center gap-2 px-4 py-3 border-b border-space-border shrink-0">
          <button
            onClick={() => setView(view === 'createProfile' ? 'profiles' : 'main')}
            className="text-space-dim hover:text-purple-400 transition-colors"
          >
            <BackArrow />
          </button>
          <span className="text-xs font-semibold uppercase tracking-widest text-space-dim">
            {view === 'profiles' ? 'Profile Settings' : 'Create Profile'}
          </span>
        </div>
      )}

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 relative">
        <AnimatePresence mode="wait">
          <motion.div
            key={view === 'main' ? activeTab : view}
            variants={slideVariants}
            initial="enter"
            animate="center"
            exit="exit"
            transition={{ duration: 0.2 }}
          >
            {view === 'main' && activeTab === 'User' && (
              <UserTab onProfileSettings={() => setView('profiles')} />
            )}
            {view === 'main' && activeTab === 'Tasks' && (
              <TasksTab jobs={jobs} processingKeys={processingKeys} />
            )}
            {view === 'main' && activeTab === 'Advanced' && <AdvancedTab />}
            {view === 'main' && activeTab === 'Preview' && (
              <PreviewTab job={selectedJob} />
            )}
            {view === 'profiles' && (
              <ProfileList
                onCreateProfile={() => setView('createProfile')}
              />
            )}
            {view === 'createProfile' && (
              <CreateProfile
                onBack={() => setView('profiles')}
                onCreated={() => setView('profiles')}
              />
            )}
          </motion.div>
        </AnimatePresence>
      </div>
    </motion.div>
  )
}
