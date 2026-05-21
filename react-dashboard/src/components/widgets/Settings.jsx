import { useState, useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { getProfiles, createProfile, getProfile, updateProfile } from '../../api'

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

// ─── User tab — profile cards ─────────────────────────────────────────────────

function ProfileCards({ onSelect, onCreateProfile }) {
  const [profiles, setProfiles] = useState([])
  const [activeId, setActiveId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    getProfiles()
      .then((data) => {
        setProfiles(data.profiles ?? [])
        setActiveId(data.active_id ?? null)
      })
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
          <button
            key={profile.id}
            onClick={() => onSelect(profile.id)}
            className={`flex flex-col gap-0.5 rounded-lg px-3 py-2.5 text-left transition-colors
              bg-white/[0.03] border hover:border-purple-500/50
              ${activeId === profile.id ? 'border-l-2 border-purple-500' : 'border-white/5'}`}
          >
            <p className="text-sm font-medium text-space-text">{profile.name || 'Unnamed'}</p>
            {(profile.first_name || profile.last_name) && (
              <p className="text-xs text-space-dim">
                {[profile.first_name, profile.last_name].filter(Boolean).join(' ')}
              </p>
            )}
          </button>
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

// ─── Profile detail view ──────────────────────────────────────────────────────

const PROVIDER_TYPES = ['openrouter', 'anthropic', 'openai', 'gemini']

function ProfileDetailView({ profileId }) {
  const [form, setForm] = useState(null)
  const [llmProviderType, setLlmProviderType] = useState('')
  const [llmModel, setLlmModel] = useState('')
  const [llmApiKey, setLlmApiKey] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState(null)
  const timerRef = useRef(null)

  useEffect(() => {
    setLoading(true)
    getProfile(profileId)
      .then((data) => {
        setForm({
          name: data.name || '',
          first_name: data.data?.first_name || '',
          last_name: data.data?.last_name || '',
          email: data.data?.email || '',
          phone: data.data?.phone || '',
          location: data.data?.location || '',
          _raw: data.data || {},
        })
        setLlmProviderType(data.llm_provider_type || '')
        setLlmModel(data.llm_model || '')
        setLlmApiKey('')
      })
      .catch(() => setStatus('Failed to load profile'))
      .finally(() => setLoading(false))
    return () => clearTimeout(timerRef.current)
  }, [profileId])

  const handleSave = async () => {
    if (!form) return
    setSaving(true)
    try {
      const firstName = form.first_name.trim()
      const lastName = form.last_name.trim()
      await updateProfile(profileId, {
        name: form.name || `${firstName} ${lastName}`.trim() || 'Unnamed',
        data: {
          ...form._raw,
          first_name: firstName,
          last_name: lastName,
          email: form.email.trim(),
          phone: form.phone.trim(),
          location: form.location.trim(),
          llm_provider_type: llmProviderType,
          llm_model: llmModel.trim(),
        },
        llm_api_key: llmApiKey,
      })
      setStatus('Saved ✓')
    } catch {
      setStatus('Save failed')
    } finally {
      setSaving(false)
      clearTimeout(timerRef.current)
      timerRef.current = setTimeout(() => setStatus(null), 2500)
    }
  }

  const field = (label, key, type = 'text') => (
    <div className="flex flex-col gap-1">
      <label className="text-xs text-space-dim">{label}</label>
      <input
        type={type}
        className={inputClass}
        value={form?.[key] ?? ''}
        onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
      />
    </div>
  )

  if (loading) return <p className="text-xs text-space-dim">Loading…</p>

  return (
    <div className="flex flex-col gap-4">
      {field('First Name', 'first_name')}
      {field('Last Name', 'last_name')}
      {field('Email', 'email')}
      {field('Phone', 'phone')}
      {field('Location', 'location')}

      <hr className="border-space-border" />
      <p className="text-xs font-semibold uppercase tracking-widest text-space-dim">LLM Provider</p>

      <div className="flex flex-col gap-1">
        <label className="text-xs text-space-dim">Provider</label>
        <select
          className={inputClass}
          value={llmProviderType}
          onChange={(e) => setLlmProviderType(e.target.value)}
        >
          <option value="">— select —</option>
          {PROVIDER_TYPES.map((p) => (
            <option key={p} value={p}>{p}</option>
          ))}
        </select>
      </div>

      <div className="flex flex-col gap-1">
        <label className="text-xs text-space-dim">Model</label>
        <input
          className={inputClass}
          value={llmModel}
          onChange={(e) => setLlmModel(e.target.value)}
          placeholder="e.g. gpt-4o"
        />
      </div>

      <div className="flex flex-col gap-1">
        <label className="text-xs text-space-dim">API Key</label>
        <input
          type="password"
          className={inputClass}
          value={llmApiKey}
          onChange={(e) => setLlmApiKey(e.target.value)}
          placeholder="Enter new key to replace existing"
        />
      </div>

      <button
        onClick={handleSave}
        disabled={saving}
        className="w-full py-2 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white text-sm font-semibold transition-colors"
      >
        {saving ? 'Saving…' : 'Save'}
      </button>

      {status && (
        <p className={`text-xs text-center ${status.includes('failed') ? 'text-red-400' : 'text-green-400'}`}>
          {status}
        </p>
      )}
    </div>
  )
}

// ─── Root ─────────────────────────────────────────────────────────────────────

const TABS = ['User', 'Tasks', 'Preview']

export default function Settings({ selectedJob, activeTab, onTabChange, jobs, processingKeys }) {
  const [view, setView] = useState('main') // 'main' | 'createProfile' | 'profileDetail'
  const [detailProfileId, setDetailProfileId] = useState(null)

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
            onClick={() => setView('main')}
            className="text-space-dim hover:text-purple-400 transition-colors"
          >
            <BackArrow />
          </button>
          <span className="text-xs font-semibold uppercase tracking-widest text-space-dim">
            {view === 'createProfile' ? 'Create Profile' : 'Edit Profile'}
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
              <ProfileCards
                onSelect={(id) => { setDetailProfileId(id); setView('profileDetail') }}
                onCreateProfile={() => setView('createProfile')}
              />
            )}
            {view === 'main' && activeTab === 'Tasks' && (
              <TasksTab jobs={jobs} processingKeys={processingKeys} />
            )}
            {view === 'main' && activeTab === 'Preview' && (
              <PreviewTab job={selectedJob} />
            )}
            {view === 'createProfile' && (
              <CreateProfile
                onBack={() => setView('main')}
                onCreated={() => setView('main')}
              />
            )}
            {view === 'profileDetail' && detailProfileId != null && (
              <ProfileDetailView profileId={detailProfileId} />
            )}
          </motion.div>
        </AnimatePresence>
      </div>
    </motion.div>
  )
}
