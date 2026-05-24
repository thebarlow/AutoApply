import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import { getProfiles, createProfile, getProfile, updateProfile, setActiveProfile, uploadProfileResume, parseProfileResume } from '../../api'
import ProfileDetailView from './ProfileDetail'

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

function MarkdownView({ url }) {
  const [text, setText] = useState(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    setText(null)
    setError(false)
    fetch(url, { signal: controller.signal })
      .then((r) => { if (!r.ok) throw new Error(); return r.text() })
      .then(setText)
      .catch((e) => { if (e.name !== 'AbortError') setError(true) })
    return () => controller.abort()
  }, [url])

  if (error) return <p className="text-xs text-space-dim">Not available.</p>
  if (text === null) return <p className="text-xs text-space-dim">Loading…</p>
  if (text === '') return <p className="text-xs text-space-dim">Not available.</p>
  return (
    <div className="text-xs text-space-text leading-relaxed [&_h1]:text-sm [&_h1]:font-semibold [&_h1]:mb-2 [&_h2]:text-xs [&_h2]:font-semibold [&_h2]:mb-1.5 [&_h3]:text-xs [&_h3]:font-semibold [&_h3]:mb-1 [&_p]:mb-2 [&_ul]:list-disc [&_ul]:list-inside [&_ul]:mb-2 [&_li]:mb-0.5 [&_strong]:font-semibold [&_em]:italic [&_code]:bg-white/10 [&_code]:rounded [&_code]:px-1">
      <ReactMarkdown>{text}</ReactMarkdown>
    </div>
  )
}

const CONTENT_TABS = ['description', 'resume', 'cover']
const CONTENT_TAB_LABELS = { description: 'Description', resume: 'Resume', cover: 'Cover Letter' }

function SubToggle({ options, value, onChange }) {
  return (
    <div className="flex gap-2">
      {options.map(({ key, label, disabled }) => (
        <button
          key={key}
          onClick={() => !disabled && onChange(key)}
          disabled={disabled}
          className={`px-3 py-1 rounded text-xs font-semibold capitalize transition-colors
            ${value === key ? 'bg-purple-600 text-white' : 'text-space-dim hover:text-space-text border border-space-border'}
            disabled:opacity-30 disabled:cursor-not-allowed`}
        >
          {label}
        </button>
      ))}
    </div>
  )
}

const ACTION_PROMPT_KEY = { description: 'extraction', resume: 'resume', cover: 'cover' }
const ACTION_PROMPT_LABEL = { extraction: 'Description Processing', resume: 'Resume Generation', cover: 'Cover Letter Generation' }

function PreviewTab({ job, promptStatus = {} }) {
  const [contentTab, setContentTab] = useState('description')
  const [descView, setDescView] = useState(() => job?.extraction_json_exists ? 'extracted' : 'raw')
  const [artifactView, setArtifactView] = useState(() => job?.resume_path ? 'pdf' : 'markdown')
  const [actionLoading, setActionLoading] = useState(false)

  const promptKey = ACTION_PROMPT_KEY[contentTab]
  const promptOk = promptStatus[promptKey] === true
  const promptMissingTitle = promptOk
    ? ''
    : `Configure the ${ACTION_PROMPT_LABEL[promptKey]} prompt in User → Prompts to enable this action.`

  // Reset all state when a different job is selected
  useEffect(() => {
    setContentTab('description')
    setDescView(job?.extraction_json_exists ? 'extracted' : 'raw')
    setArtifactView(job?.resume_path ? 'pdf' : 'markdown')
    setActionLoading(false)
  }, [job?.job_key])

  // Reset artifactView when switching between resume/cover tabs
  const handleContentTab = (tab) => {
    setContentTab(tab)
    if (tab === 'resume') setArtifactView(job?.resume_path ? 'pdf' : 'markdown')
    else if (tab === 'cover') setArtifactView(job?.cover_path ? 'pdf' : 'markdown')
  }

  const handleAction = async () => {
    if (!job || actionLoading || !promptOk) return
    const urlMap = {
      description: `/api/jobs/${job.job_key}/description/extract`,
      resume: `/api/jobs/${job.job_key}/generate/resume`,
      cover: `/api/jobs/${job.job_key}/generate/cover`,
    }
    setActionLoading(true)
    try {
      await fetch(urlMap[contentTab], { method: 'POST' })
    } finally {
      setActionLoading(false)
    }
  }

  if (!job) return null

  const score = job.final_score != null ? Math.round(job.final_score * 100) + '%' : '—'
  const stateLabel = STATE_LABELS[job.state] ?? job.state
  const hasResume = !!job.resume_path
  const hasCover = !!job.cover_path

  return (
    <div className="flex flex-col gap-4">
      {/* Info */}
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

      {/* Content tab bar */}
      <div className="flex items-center gap-2">
        {CONTENT_TABS.map((tab) => {
          const disabled = false
          return (
            <button
              key={tab}
              onClick={() => !disabled && handleContentTab(tab)}
              disabled={disabled}
              className={`px-3 py-1 rounded text-xs font-semibold transition-colors
                ${contentTab === tab && !disabled ? 'bg-purple-600 text-white' : 'text-space-dim hover:text-space-text border border-space-border'}
                disabled:opacity-30 disabled:cursor-not-allowed`}
            >
              {CONTENT_TAB_LABELS[tab]}
            </button>
          )
        })}
        <button
          onClick={() => {
            if (job.url) window.open(job.url, '_blank')
            fetch(`/api/jobs/${job.job_key}/apply`, { method: 'POST' })
              .then(res => { if (!res.ok) console.error(`Apply failed: ${res.status}`) })
              .catch(err => console.error('Apply request failed:', err))
          }}
          className="ml-auto px-3 py-1 rounded text-xs font-semibold transition-colors bg-[#198754] text-white hover:opacity-90"
        >
          {hasResume ? 'Apply' : 'View Post'}
        </button>
      </div>

      <hr className="border-space-border" />

      {/* Content area */}
      {contentTab === 'description' && (
        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <SubToggle
              options={[
                { key: 'raw', label: 'Raw' },
                { key: 'extracted', label: 'Processed', disabled: !job.extraction_json_exists },
              ]}
              value={descView}
              onChange={setDescView}
            />
            <button
              onClick={handleAction}
              disabled={actionLoading || !promptOk}
              title={promptMissingTitle}
              className="px-3 py-1 rounded text-xs font-semibold transition-colors bg-purple-600 hover:bg-purple-500 text-white disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {actionLoading ? '…' : !promptOk ? 'Prompt not set' : job.extraction_json_exists ? 'Reprocess' : 'Process'}
            </button>
          </div>
          {descView === 'raw' && (
            <p className="text-xs text-space-dim leading-relaxed whitespace-pre-wrap">
              {job.description || 'No description available.'}
            </p>
          )}
          {descView === 'extracted' && (
            job.extraction
              ? <ExtractionView data={job.extraction} />
              : <p className="text-xs text-space-dim">No extraction yet.</p>
          )}
        </div>
      )}

      {(contentTab === 'resume' || contentTab === 'cover') && (
        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <SubToggle
              options={[
                { key: 'markdown', label: 'Markdown' },
                { key: 'pdf', label: 'PDF' },
              ]}
              value={artifactView}
              onChange={setArtifactView}
            />
            <button
              onClick={handleAction}
              disabled={actionLoading || !promptOk}
              title={promptMissingTitle}
              className="px-3 py-1 rounded text-xs font-semibold transition-colors bg-purple-600 hover:bg-purple-500 text-white disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {actionLoading ? '…' : !promptOk ? 'Prompt not set' : (contentTab === 'resume' ? hasResume : hasCover) ? 'Regenerate' : 'Generate'}
            </button>
          </div>
          {artifactView === 'markdown' && (
            <MarkdownView
              url={contentTab === 'resume'
                ? `/api/jobs/${job.job_key}/resume/markdown`
                : `/api/jobs/${job.job_key}/cover/markdown`}
            />
          )}
          {artifactView === 'pdf' && (
            <iframe
              src={contentTab === 'resume'
                ? `/api/jobs/${job.job_key}/resume`
                : `/api/jobs/${job.job_key}/cover`}
              className="w-full h-[600px] rounded border border-space-border"
              title={contentTab === 'resume' ? 'Resume PDF' : 'Cover Letter PDF'}
            />
          )}
        </div>
      )}
    </div>
  )
}

// ─── User tab ─────────────────────────────────────────────────────────────────

const PROVIDER_TYPES = ['openrouter', 'anthropic', 'openai', 'gemini']

function CreateProfile({ onBack, onCreated }) {
  const [step, setStep] = useState(1)
  const [createdId, setCreatedId] = useState(null)

  // Step 1
  const [name, setName] = useState('')
  const [providerType, setProviderType] = useState('')
  const [model, setModel] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [savingStep1, setSavingStep1] = useState(false)
  const [error, setError] = useState(null)

  // Step 2
  const [file, setFile] = useState(null)
  const [parsing, setParsing] = useState(false)
  const [parseError, setParseError] = useState(null)

  const handleStep1 = async () => {
    const trimmed = name.trim()
    if (!trimmed) { setError('Name is required'); return }
    if (!providerType) { setError('LLM provider is required'); return }
    if (!model.trim()) { setError('Model is required'); return }
    if (!apiKey.trim()) { setError('API key is required'); return }
    setSavingStep1(true)
    setError(null)
    try {
      const profile = await createProfile(trimmed)
      await updateProfile(profile.id, {
        name: trimmed,
        data: { llm_provider_type: providerType, llm_model: model.trim() },
        llm_api_key: apiKey.trim(),
      })
      setCreatedId(profile.id)
      setStep(2)
    } catch {
      setError('Failed to create profile')
    } finally {
      setSavingStep1(false)
    }
  }

  const handleUploadAndParse = async () => {
    if (!file) { setParseError('Select a file first'); return }
    setParsing(true)
    setParseError(null)
    try {
      const { path, filename } = await uploadProfileResume(file)
      const current = await getProfile(createdId)
      await updateProfile(createdId, {
        name: current.name,
        data: { ...current.data, resume_path: path, resume_filename: filename },
      })
      await parseProfileResume(createdId)
      onCreated({ id: createdId, name: current.name })
    } catch (e) {
      setParseError(e?.message?.includes('400') ? 'Parsing failed — check LLM config and prompt' : 'Upload/parse failed')
    } finally {
      setParsing(false)
    }
  }

  const handleSkip = () => onCreated({ id: createdId, name })

  if (step === 1) {
    return (
      <div className="flex flex-col gap-4">
        <p className="text-xs text-space-dim">Step 1 of 2 — Profile shell</p>

        <div className="flex flex-col gap-1">
          <label className="text-xs text-space-dim">Profile Name</label>
          <input
            className={inputClass}
            value={name}
            onChange={(e) => { setName(e.target.value); setError(null) }}
            placeholder="e.g. Software Engineer"
          />
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-xs text-space-dim">LLM Provider</label>
          <select className={inputClass} value={providerType} onChange={(e) => setProviderType(e.target.value)}>
            <option value="">— select —</option>
            {PROVIDER_TYPES.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-xs text-space-dim">Model</label>
          <input
            className={inputClass}
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder="e.g. gpt-4o-mini"
          />
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-xs text-space-dim">API Key</label>
          <input
            type="password"
            className={inputClass}
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="sk-…"
          />
        </div>

        {error && <p className="text-xs text-red-400">{error}</p>}

        <div className="flex gap-2">
          <button
            onClick={handleStep1}
            disabled={savingStep1}
            className="flex-1 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white text-sm font-semibold transition-colors"
          >
            {savingStep1 ? 'Saving…' : 'Continue'}
          </button>
          <button onClick={onBack} className="px-4 py-2 rounded-lg border border-space-border text-sm text-space-dim hover:text-space-text transition-colors">
            Cancel
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-xs text-space-dim">Step 2 of 2 — Upload Master Resume (optional)</p>
      <p className="text-xs text-space-dim">
        Upload a PDF or Markdown resume to auto-populate this profile. Skip to fill in fields manually.
      </p>

      <div className="flex flex-col gap-1">
        <label className="text-xs text-space-dim">Master Resume (.pdf or .md)</label>
        <input
          type="file"
          accept=".pdf,.md"
          onChange={(e) => { setFile(e.target.files?.[0] ?? null); setParseError(null) }}
          className="text-xs text-space-text file:mr-2 file:px-3 file:py-1.5 file:rounded-lg file:border file:border-space-border file:bg-white/5 file:text-space-text file:hover:border-purple-500/50 file:cursor-pointer"
        />
      </div>

      {parseError && <p className="text-xs text-red-400">{parseError}</p>}

      <div className="flex gap-2">
        <button
          onClick={handleUploadAndParse}
          disabled={parsing || !file}
          className="flex-1 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white text-sm font-semibold transition-colors"
        >
          {parsing ? 'Parsing…' : 'Upload & Parse'}
        </button>
        <button
          onClick={handleSkip}
          disabled={parsing}
          className="px-4 py-2 rounded-lg border border-space-border text-sm text-space-dim hover:text-space-text transition-colors disabled:opacity-50"
        >
          Skip
        </button>
      </div>
    </div>
  )
}

// ─── User tab — profile cards ─────────────────────────────────────────────────

function ProfileCards({ onSelect, onCreateProfile }) {
  const [profiles, setProfiles] = useState([])
  const [activeId, setActiveId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [settingActive, setSettingActive] = useState(null)

  useEffect(() => {
    getProfiles()
      .then((data) => {
        setProfiles(data.profiles ?? [])
        setActiveId(data.active_id ?? null)
      })
      .catch(() => setError('Failed to load profiles'))
      .finally(() => setLoading(false))
  }, [])

  const handleSetActive = async (id) => {
    setSettingActive(id)
    try {
      await setActiveProfile(id)
      setActiveId(id)
      window.dispatchEvent(new CustomEvent('auto-apply:prompt-status-stale'))
    } finally {
      setSettingActive(null)
    }
  }

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
            className={`flex items-center gap-2 rounded-lg border border-white/5 border-l-4 bg-white/[0.03]
              ${activeId === profile.id ? 'border-l-purple-500' : 'border-l-transparent'}`}
          >
            <button
              onClick={() => onSelect(profile.id)}
              className="flex-1 flex flex-col gap-0.5 px-3 py-2.5 text-left hover:bg-white/[0.03] transition-colors rounded-lg min-w-0"
            >
              <p className="text-sm font-medium text-space-text">{profile.name || 'Unnamed'}</p>
              {(profile.first_name || profile.last_name) && (
                <p className="text-xs text-space-dim">
                  {[profile.first_name, profile.last_name].filter(Boolean).join(' ')}
                </p>
              )}
            </button>
            <div className="pr-2 shrink-0">
              {activeId === profile.id
                ? <span className="text-xs font-medium text-purple-400">Active</span>
                : (
                  <button
                    onClick={() => handleSetActive(profile.id)}
                    disabled={settingActive === profile.id}
                    className="text-xs text-space-dim hover:text-space-text border border-space-border hover:border-purple-500/50 rounded px-2 py-0.5 transition-colors disabled:opacity-50"
                  >
                    {settingActive === profile.id ? '…' : 'Set Active'}
                  </button>
                )
              }
            </div>
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


// ─── Root ─────────────────────────────────────────────────────────────────────

const TABS = ['User', 'Preview']

export default function Settings({ selectedJob, activeTab, onTabChange, promptStatus = {} }) {
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

            {view === 'main' && activeTab === 'Preview' && (
              <PreviewTab job={selectedJob} promptStatus={promptStatus} />
            )}
            {view === 'createProfile' && (
              <CreateProfile
                onBack={() => setView('main')}
                onCreated={() => setView('main')}
              />
            )}
            {view === 'profileDetail' && detailProfileId != null && (
              <ProfileDetailView profileId={detailProfileId} onDelete={() => setView('main')} />
            )}
          </motion.div>
        </AnimatePresence>
      </div>
    </motion.div>
  )
}
