import { useState, useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import { getProfiles, createProfile, getProfile, updateProfile, setActiveProfile, uploadProfileResume, parseProfileResume, markJobActionSeen, deleteJob, updateJobState, updateJobFields, flagJob, getOwnedSkills } from '../../api'
import DocumentModal from './DocumentModal'
import SkillChipModal from './SkillChipModal'
import ProfileDetailView from './ProfileDetail'
import ProfileEditorModal from './ProfileEditorModal'
import UserHome from './UserHome'
import { WarningIcon } from '../shared/JobCard'
import GatedButton from '../shared/GatedButton'
import HelpIcon from '../shared/HelpIcon'

// ─── Icons ────────────────────────────────────────────────────────────────────

function BackArrow() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10 12L6 8l4-4" />
    </svg>
  )
}

// Copies the job's stable key to the clipboard (e.g. for the Admin résumé
// comparison tool, which takes a job_key the UI otherwise doesn't surface).
function CopyKeyButton({ jobKey }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(jobKey)
      setCopied(true)
      setTimeout(() => setCopied(false), 1200)
    } catch {
      /* clipboard unavailable (e.g. insecure context) — ignore */
    }
  }
  return (
    <button
      type="button"
      onClick={copy}
      title={`Copy job key: ${jobKey}`}
      className="text-xs text-space-dim hover:text-purple-400 border border-space-border rounded px-1.5 py-0.5 transition-colors"
    >{copied ? 'Copied!' : 'Copy key'}</button>
  )
}

function FlagButton({ flagged, onClick }) {
  return (
    <button
      onClick={onClick}
      title={flagged ? 'Remove flag' : 'Flag this job'}
      className="shrink-0 text-space-dim hover:text-red-400 transition-colors"
    >
      {flagged ? (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="#ef4444" stroke="#ef4444" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/>
          <line x1="4" y1="22" x2="4" y2="15"/>
        </svg>
      ) : (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/>
          <line x1="4" y1="22" x2="4" y2="15"/>
        </svg>
      )}
    </button>
  )
}

function useEscape(active, handler) {
  useEffect(() => {
    if (!active) return
    const onKey = (e) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        handler()
      }
    }
    document.addEventListener('keydown', onKey, true)
    return () => document.removeEventListener('keydown', onKey, true)
  }, [active, handler])
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

const STATE_LABELS = { new: 'New', pending_review: 'Pending Review', ready: 'Ready', applied: 'Applied', contact: 'In Contact', rejected: 'Rejected', deleted: 'Deleted' }
const ALL_STATES = Object.keys(STATE_LABELS)

function ExtractionView({ data }) {
  const metaKeys = ['seniority', 'role_type', 'domain', 'work_arrangement', 'employment_type']
  const meta = metaKeys.map((k) => data[k]).filter((v) => v && String(v).trim())

  const chipGroups = [
    { key: 'required_skills', label: 'Required Skills' },
    { key: 'preferred_skills', label: 'Preferred Skills' },
    { key: 'tech_stack', label: 'Tech Stack' },
  ]
  const bulletGroups = [
    { key: 'key_responsibilities', label: 'Responsibilities' },
    { key: 'company_signals', label: 'Company Signals' },
  ]
  const asList = (v) => (Array.isArray(v) ? v.filter((x) => x && String(x).trim()) : [])

  const [modalSkill, setModalSkill] = useState(null)
  const [owned, setOwned] = useState(new Set())
  const [ownRefresh, setOwnRefresh] = useState(0)

  // All distinct skill tokens across the three chip groups.
  const allSkills = [...new Set(chipGroups.flatMap(({ key }) => asList(data[key])))]
  const allSkillsKey = allSkills.join('')  // stable dep: refetch only when the set changes

  useEffect(() => {
    if (allSkills.length === 0) { setOwned(new Set()); return }
    let active = true
    getOwnedSkills(allSkills)
      .then((res) => { if (active) setOwned(new Set(res.owned)) })
      .catch(() => { if (active) setOwned(new Set()) })
    return () => { active = false }
  }, [allSkillsKey, ownRefresh])

  // Three-state chip styling: green = I have it; amber = a required skill I lack
  // (a résumé gap); neutral = anything else I don't have.
  const chipClass = (v, groupKey) => {
    if (owned.has(v)) return 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/40 hover:bg-emerald-500/25'
    if (groupKey === 'required_skills') return 'bg-amber-500/15 text-amber-300 border border-amber-500/40 hover:bg-amber-500/25'
    return 'bg-white/10 text-space-text border border-transparent hover:bg-white/20'
  }

  return (
    <div className="flex flex-col gap-3">
      {meta.length > 0 && (
        <p className="text-xs text-space-text text-center border-b border-space-border pb-3">{meta.join(' · ')}</p>
      )}

      {chipGroups.map(({ key, label }) => {
        const items = asList(data[key])
        if (items.length === 0) return null
        return (
          <div key={key}>
            <p className="text-xs font-semibold text-space-dim mb-1">{label}</p>
            <div className="flex flex-wrap gap-1">
              {items.map((v, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => setModalSkill(v)}
                  className={`inline-block rounded px-1.5 py-0.5 text-xs transition-colors ${chipClass(v, key)}`}
                >
                  {owned.has(v) && <span className="mr-0.5">✓</span>}
                  {v}
                </button>
              ))}
            </div>
          </div>
        )
      })}

      <p className="flex flex-wrap gap-x-3 gap-y-0.5 text-[10px] text-space-dim">
        <span><span className="text-emerald-300">✓ have</span></span>
        <span className="text-amber-300">required gap</span>
        <span>other</span>
      </p>

      {bulletGroups.map(({ key, label }) => {
        const items = asList(data[key])
        if (items.length === 0) return null
        return (
          <div key={key}>
            <p className="text-xs font-semibold text-space-dim mb-1">{label}</p>
            <ul className="list-disc list-inside text-xs space-y-0.5 text-space-text">
              {items.map((v, i) => <li key={i}>{v}</li>)}
            </ul>
          </div>
        )
      })}

      {modalSkill && (
        <SkillChipModal
          skill={modalSkill}
          isOwned={owned.has(modalSkill)}
          onClose={() => setModalSkill(null)}
          onChanged={() => setOwnRefresh((n) => n + 1)}
        />
      )}
    </div>
  )
}

export function MarkdownView({ url }) {
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

const CONTENT_TABS = ['description', 'resume', 'cover', 'score']
const CONTENT_TAB_LABELS = { description: 'Description', resume: 'Resume', cover: 'Cover Letter', score: 'Score' }

export function SubToggle({ options, value, onChange }) {
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

function TurnEntry({ entry, hue, turnUrl, isLast, showDivider }) {
  const [viewOpen, setViewOpen] = useState(false)
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-xs font-semibold text-space-dim">{entry.source === 'user_feedback' ? 'Your feedback' : `Turn ${entry.turn}`}</span>
        <span style={{ color: `hsl(${hue}, 75%, 55%)` }} className="text-xs font-bold tabular-nums">
          {(entry.score * 10).toFixed(1)}/10
        </span>
        {entry.passed
          ? <span className="text-xs text-emerald-400">✓ passed</span>
          : isLast
            ? <span className="text-xs text-space-dim/50">limit reached</span>
            : null
        }
        <button
          onClick={() => setViewOpen(v => !v)}
          className="ml-auto text-xs text-space-dim hover:text-space-text border border-space-border px-2 py-0.5 rounded transition-colors"
        >
          {viewOpen ? 'Hide' : 'View'}
        </button>
      </div>
      {entry.issues && entry.issues.length > 0 && (
        <ul className="text-xs text-space-text space-y-0.5">
          {entry.issues.map((issue, i) => (
            <li key={i} className="flex gap-1.5">
              <span className="text-space-dim/70 shrink-0">[{issue.category}]</span>
              <span>{issue.description}</span>
            </li>
          ))}
        </ul>
      )}
      {viewOpen && <MarkdownView url={turnUrl} />}
      {showDivider && <hr className="border-space-border" />}
    </div>
  )
}

const ACTION_PROMPT_KEY = { description: 'extraction', resume: 'resume', cover: 'cover', score: 'scoring' }
const ACTION_PROMPT_LABEL = { extraction: 'Description Processing', resume: 'Resume Generation', cover: 'Cover Letter Generation', scoring: 'Scoring' }

// Reduce a justification field (string | {raised, lowered} | undefined) to two arrays.
function _splitJustification(j) {
  if (!j) return { raised: [], lowered: [] }
  if (typeof j === 'string') return { raised: [j], lowered: [] }
  return {
    raised: Array.isArray(j.raised) ? j.raised : [],
    lowered: Array.isArray(j.lowered) ? j.lowered : [],
  }
}

function EditFieldsModal({ job, onClose }) {
  const [fields, setFields] = useState({
    title: job.title || '',
    description: job.description || '',
    company: job.company || '',
    location: job.location || '',
    salary: job.salary || '',
    url: job.url || '',
  })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [popOut, setPopOut] = useState(false)

  useEscape(popOut, () => setPopOut(false))
  useEscape(!popOut, onClose)

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    try {
      await updateJobFields(job.job_key, fields)
      onClose()
    } catch (e) {
      setError(e?.message || 'Save failed')
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-[#0f0f1a] border border-space-border rounded-xl w-[90%] max-w-md p-5 flex flex-col gap-3 shadow-2xl max-h-[90vh] overflow-y-auto">
        <p className="text-sm font-semibold text-space-text">Edit job</p>

        <label className="text-xs text-space-dim">Title</label>
        <input
          value={fields.title}
          onChange={(e) => setFields(f => ({ ...f, title: e.target.value }))}
          className={inputClass}
        />

        <div className="flex items-center justify-between">
          <label className="text-xs text-space-dim">Description</label>
          <button
            type="button"
            onClick={() => setPopOut(true)}
            title="Expand description"
            className="text-space-dim hover:text-space-text transition-colors p-0.5"
          >
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-3.5 h-3.5">
              <path d="M1 6V1h5M10 1h5v5M15 10v5h-5M6 15H1v-5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </button>
        </div>
        <textarea
          value={fields.description}
          onChange={(e) => setFields(f => ({ ...f, description: e.target.value }))}
          rows={6}
          className={inputClass}
        />

        <label className="text-xs text-space-dim">Company</label>
        <input
          value={fields.company}
          onChange={(e) => setFields(f => ({ ...f, company: e.target.value }))}
          className={inputClass}
        />

        <label className="text-xs text-space-dim">Location</label>
        <input
          value={fields.location}
          onChange={(e) => setFields(f => ({ ...f, location: e.target.value }))}
          className={inputClass}
        />

        <label className="text-xs text-space-dim">Salary</label>
        <input
          value={fields.salary}
          onChange={(e) => setFields(f => ({ ...f, salary: e.target.value }))}
          className={inputClass}
        />

        <label className="text-xs text-space-dim">URL</label>
        <input
          value={fields.url}
          onChange={(e) => setFields(f => ({ ...f, url: e.target.value }))}
          className={inputClass}
        />

        {error && <p className="text-xs text-red-400">{error}</p>}

        <div className="flex gap-2 mt-2">
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="flex-1 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white text-sm font-semibold"
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            className="px-4 py-2 rounded-lg border border-space-border text-sm text-space-dim hover:text-space-text"
          >
            Cancel
          </button>
        </div>
      </div>

      {popOut && (
        <div className="fixed inset-0 z-[60] flex flex-col bg-[#0a0a14]">
          <div className="flex items-center justify-between px-6 py-4 border-b border-white/10 shrink-0">
            <span className="text-sm font-semibold text-space-text">Description</span>
            <button
              type="button"
              onClick={() => setPopOut(false)}
              className="text-space-dim hover:text-white transition-colors"
              aria-label="Collapse description"
            >
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-4 h-4">
                <path d="M6 1v5H1M15 6h-5V1M1 10h5v5M10 15v-5h5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </button>
          </div>
          <textarea
            className="flex-1 w-full bg-transparent text-space-text p-6 resize-none focus:outline-none font-mono text-sm"
            value={fields.description}
            onChange={(e) => setFields(f => ({ ...f, description: e.target.value }))}
            autoFocus
          />
        </div>
      )}
    </div>
  )
}

function ScoreView({ job }) {
  const score = job.final_score
  if (score == null) {
    return <p className="text-xs text-space-dim">Not scored yet. Click Calculate to score this job.</p>
  }
  const display = (score * 10).toFixed(1)
  // Red (hue 0) → Green (hue 120) gradient
  const hue = Math.round(score * 120)
  const color = `hsl(${hue}, 75%, 55%)`

  const fit = _splitJustification(job.score_justification?.fit)
  const des = _splitJustification(job.score_justification?.desirability)
  const raised = [...fit.raised, ...des.raised]
  const lowered = [...fit.lowered, ...des.lowered]

  const fitPct = job.fit_score != null ? (job.fit_score * 10).toFixed(1) : '—'
  const desPct = job.desirability_score != null ? (job.desirability_score * 10).toFixed(1) : '—'

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-4">
        <div
          className="text-5xl font-bold leading-none tabular-nums"
          style={{ color }}
        >
          {display}
        </div>
        <div className="flex flex-col gap-0.5 text-xs text-space-dim">
          <span>Fit: <span className="text-space-text font-medium">{fitPct}</span></span>
          <span>Desirability: <span className="text-space-text font-medium">{desPct}</span></span>
          <span className="opacity-70">out of 10.0</span>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="flex flex-col gap-1.5 rounded-lg border border-space-border p-3 bg-white/[0.02]">
          <p className="text-xs font-semibold text-emerald-400">Raised</p>
          {raised.length === 0
            ? <p className="text-xs text-space-dim italic">None</p>
            : <ul className="text-xs text-space-text space-y-1 list-disc list-inside">
                {raised.map((r, i) => <li key={i}>{r}</li>)}
              </ul>
          }
        </div>
        <div className="flex flex-col gap-1.5 rounded-lg border border-space-border p-3 bg-white/[0.02]">
          <p className="text-xs font-semibold text-red-400">Lowered</p>
          {lowered.length === 0
            ? <p className="text-xs text-space-dim italic">None</p>
            : <ul className="text-xs text-space-text space-y-1 list-disc list-inside">
                {lowered.map((r, i) => <li key={i}>{r}</li>)}
              </ul>
          }
        </div>
      </div>
    </div>
  )
}

function PreviewTab({ job, promptStatus = {}, actionsInFlight = new Set(), onJobDeleted }) {
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState(null)
  const [stateChanging, setStateChanging] = useState(false)
  const [flagging, setFlagging] = useState(false)

  const handleFlag = async () => {
    if (!job || flagging) return
    setFlagging(true)
    try {
      await flagJob(job.job_key, !job.flagged)
    } catch { /* SSE will sync; ignore */ }
    finally {
      setFlagging(false)
    }
  }

  const [showEditFields, setShowEditFields] = useState(false)
  const [expandDoc, setExpandDoc] = useState(null) // null | 'resume' | 'cover'

  useEffect(() => {
    if (!confirmDelete) return
    const onKey = (e) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        setConfirmDelete(false)
      }
    }
    document.addEventListener('keydown', onKey, true)
    return () => document.removeEventListener('keydown', onKey, true)
  }, [confirmDelete])

  const handleDelete = async () => {
    if (!job) return
    setDeleting(true)
    setDeleteError(null)
    try {
      await deleteJob(job.job_key)
      onJobDeleted?.(job.job_key)
    } catch {
      setDeleteError('Delete failed')
      setDeleting(false)
    }
  }
  const [contentTab, setContentTab] = useState('description')
  const [artifactView, setArtifactView] = useState(() => job?.resume_path ? 'pdf' : 'markdown')
  const [localLoadingTabs, setLocalLoadingTabs] = useState(() => new Set())
  const [actionError, setActionError] = useState(null)
  // Bump on each completed (re)generation to bust iframe / fetch caches.
  const [artifactNonce, setArtifactNonce] = useState({ resume: 0, cover: 0 })
  const prevInFlight = useRef(new Set())

  useEffect(() => {
    const prev = prevInFlight.current
    const bumps = {}
    // Generation keys ('resume'/'cover') and feedback/refine keys
    // ('resume_refine', 'resume_eval', 'cover_refine', 'cover_eval') all bump
    // the nonce for their doc type on present->absent so the PDF/MD preview
    // refreshes after generation OR a feedback-triggered regeneration.
    for (const k of prev) {
      if (actionsInFlight.has(k)) continue // still running
      const doc = k === 'resume' || k === 'cover' ? k : k.replace(/_(refine|eval)$/, '')
      if (doc === 'resume' || doc === 'cover') bumps[doc] = true
    }
    prevInFlight.current = new Set(actionsInFlight)
    if (Object.keys(bumps).length > 0) {
      setArtifactNonce((cur) => ({
        resume: bumps.resume ? cur.resume + 1 : cur.resume,
        cover: bumps.cover ? cur.cover + 1 : cur.cover,
      }))
    }
  }, [actionsInFlight])
  // SSE-driven actions use server action names; tabs use the same keys.
  const isLoading = (tab) =>
    localLoadingTabs.has(tab) || actionsInFlight.has(tab)
  const actionLoading = isLoading(contentTab)

  const promptKey = ACTION_PROMPT_KEY[contentTab]
  const promptOk = promptStatus[promptKey] === true
  const promptMissingTitle = promptOk
    ? ''
    : `Configure the ${ACTION_PROMPT_LABEL[promptKey]} prompt in User → Prompts to enable this action.`

  const pendingReview = new Set(job?.pending_review_actions || [])
  const isPendingReview = (tab) => pendingReview.has(tab)

  // Auto-clear pending-review for whichever subtab the user is currently viewing.
  useEffect(() => {
    if (!job) return
    if (pendingReview.has(contentTab)) {
      markJobActionSeen(job.job_key, contentTab).catch(() => {})
    }
  }, [job?.job_key, contentTab, job?.pending_review_actions?.join(',')])

  // Reset all state when a different job is selected
  useEffect(() => {
    setContentTab('description')
    setArtifactView(job?.resume_path ? 'pdf' : 'markdown')
    setLocalLoadingTabs(new Set())
    setActionError(null)
    setArtifactNonce({ resume: 0, cover: 0 })
    prevInFlight.current = new Set()
    setConfirmDelete(false)
    setDeleting(false)
    setDeleteError(null)
    setStateChanging(false)
    setShowEditFields(false)
    setExpandDoc(null)
    setFlagging(false)
  }, [job?.job_key])

  // Reset artifactView when switching between resume/cover tabs
  const handleContentTab = (tab) => {
    setContentTab(tab)
    setActionError(null)
    if (tab === 'resume') setArtifactView(job?.resume_path ? 'pdf' : 'markdown')
    else if (tab === 'cover') setArtifactView(job?.cover_path ? 'pdf' : 'markdown')
  }

  const handleStateChange = async (newState) => {
    if (!job || stateChanging || newState === job.state) return
    setStateChanging(true)
    try {
      await updateJobState(job.job_key, newState)
    } catch { /* SSE will sync state; ignore errors silently */ }
    finally {
      setStateChanging(false)
    }
  }

  const handleAction = async () => {
    if (!job || actionLoading || !promptOk) return
    const urlMap = {
      description: `/api/jobs/${job.job_key}/description/extract`,
      resume: `/api/jobs/${job.job_key}/generate/resume`,
      cover: `/api/jobs/${job.job_key}/generate/cover`,
      score: `/api/jobs/${job.job_key}/score`,
    }
    const tab = contentTab
    setLocalLoadingTabs((prev) => {
      const next = new Set(prev)
      next.add(tab)
      return next
    })
    setActionError(null)
    try {
      const res = await fetch(urlMap[tab], { method: 'POST' })
      if (!res.ok) {
        let detail = `Request failed (${res.status})`
        let body = null
        try {
          body = await res.json()
          if (body?.detail) detail = body.detail
        } catch { /* non-JSON body */ }
        // Out-of-credits: surface the app-wide signal (toast + balance refresh)
        // since this path bypasses api.js's _fetch 402 handler.
        if (res.status === 402 && body?.error === 'insufficient_credits') {
          window.dispatchEvent(new CustomEvent('auto-apply:credits-error', { detail: body }))
          window.dispatchEvent(new Event('auto-apply:credits-stale'))
          detail = "You're out of credits — purchase more to continue."
        }
        setActionError(detail)
      }
    } catch (e) {
      setActionError(e?.message || 'Request failed')
    } finally {
      setLocalLoadingTabs((prev) => {
        const next = new Set(prev)
        next.delete(tab)
        return next
      })
    }
  }

  if (!job) return null

  const score = job.final_score != null ? Math.round(job.final_score * 100) + '%' : '—'
  const stateLabel = STATE_LABELS[job.state] ?? job.state
  const hasResume = !!job.resume_path
  const hasCover = !!job.cover_path

  // Cache-bust artifacts on both local (re)generation AND server-side updates
  // (e.g. background refinement, which bumps {doc}_generated_at without touching
  // the local in-flight nonce). Without the timestamp, the iframe keeps showing
  // a stale PDF after refinement rewrites it.
  const resumeCacheKey = `${artifactNonce.resume}-${encodeURIComponent(job.resume_generated_at || '')}`
  const coverCacheKey = `${artifactNonce.cover}-${encodeURIComponent(job.cover_generated_at || '')}`

  return (
    <div className="flex flex-col gap-4">
      {job.last_result_error && (
        <div className="bg-red-900/20 border border-red-500/40 rounded-lg px-3 py-2 flex items-start gap-2">
          <div className="mt-0.5"><WarningIcon /></div>
          <div className="min-w-0 flex-1">
            <p className="text-xs font-semibold text-red-400">Last LLM call failed</p>
            <p className="text-xs text-red-200/80 break-words mt-0.5">
              {job.last_result_error.length > 400 ? job.last_result_error.slice(0, 400) + '…' : job.last_result_error}
            </p>
          </div>
        </div>
      )}
      {/* Info */}
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-start gap-2">
            <h2 className="text-base font-semibold text-space-text leading-tight flex-1">{job.title || '(no title)'}</h2>
            <FlagButton flagged={!!job.flagged} onClick={handleFlag} />
          </div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1.5">
            {job.company && <span className="text-xs text-space-dim">{job.company}</span>}
            {job.location && <span className="text-xs text-space-dim">{job.location}</span>}
            {job.salary && <span className="text-xs text-space-dim">{job.salary}</span>}
            <span className="text-xs font-semibold text-purple-400">{score}</span>
            <select
              value={job.state}
              onChange={(e) => handleStateChange(e.target.value)}
              disabled={stateChanging}
              title="Change job status"
              className="text-xs text-space-dim bg-transparent border border-space-border rounded px-1.5 py-0.5 focus:outline-none focus:border-purple-500 transition-colors disabled:opacity-50 cursor-pointer"
            >
              {ALL_STATES.map((s) => (
                <option key={s} value={s} className="bg-[#0f0f1a]">{STATE_LABELS[s]}</option>
              ))}
            </select>
            <CopyKeyButton jobKey={job.job_key} />
          </div>
        </div>
        <div className="flex flex-col gap-1 shrink-0">
          <button
            type="button"
            onClick={() => {
              if (job.url) window.open(job.url, '_blank')
              fetch(`/api/jobs/${job.job_key}/apply`, { method: 'POST' })
                .then(res => { if (!res.ok) console.error(`Apply failed: ${res.status}`) })
                .catch(err => console.error('Apply request failed:', err))
            }}
            className="px-3 py-1 rounded text-xs font-semibold transition-colors bg-[#198754] text-white hover:opacity-90"
          >
            {hasResume ? 'Apply' : 'View Post'}
          </button>
          <button
            type="button"
            onClick={() => setShowEditFields(true)}
            title="Edit job fields"
            className="px-3 py-1 rounded text-xs font-semibold transition-colors border border-space-border text-space-dim hover:text-space-text"
          >
            Edit
          </button>
        </div>
      </div>

      <hr className="border-space-border" />

      {/* Content tab bar */}
      <div className="flex items-center gap-2">
        {CONTENT_TABS.map((tab) => {
          const disabled = false
          const tabLoading = isLoading(tab)
          const tabPending = !tabLoading && isPendingReview(tab)
          return (
            <button
              key={tab}
              onClick={() => !disabled && handleContentTab(tab)}
              disabled={disabled}
              className={`px-3 py-1 rounded text-xs font-semibold transition-colors
                ${contentTab === tab && !disabled ? 'bg-purple-600 text-white' : 'text-space-dim hover:text-space-text border border-space-border'}
                ${tabLoading ? 'shiny-border' : ''}
                ${tabPending ? 'review-pending' : ''}
                disabled:opacity-30 disabled:cursor-not-allowed`}
            >
              {CONTENT_TAB_LABELS[tab]}
            </button>
          )
        })}
        <button
          onClick={() => { setDeleteError(null); setConfirmDelete(true) }}
          title="Delete job"
          className="ml-auto px-3 py-1 rounded text-xs font-semibold transition-colors border border-red-500/30 text-red-400 hover:bg-red-500/10"
        >
          Delete
        </button>
      </div>

      <hr className="border-space-border" />

      {/* Content area */}
      {contentTab === 'description' && (
        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-end">
            <GatedButton
              action="score"
              onClick={handleAction}
              disabled={actionLoading || !promptOk}
              title={promptMissingTitle || undefined}
              className="px-3 py-1 rounded text-xs font-semibold transition-colors bg-purple-600 hover:bg-purple-500 text-white disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {actionLoading ? '…' : !promptOk ? 'Prompt not set' : job.extraction_json_exists ? 'Reprocess' : 'Process'}
            </GatedButton>
          </div>
          {actionError && <p className="text-xs text-red-400 break-words">{actionError}</p>}

          {job.extraction
            ? <ExtractionView data={job.extraction} />
            : <p className="text-xs text-space-dim">No extraction yet.</p>}

          <details className="border-t-2 border-space-border pt-2">
            <summary className="text-xs font-bold text-center text-space-dim cursor-pointer select-none hover:text-space-text">
              Raw Description
            </summary>
            <p className="mt-2 text-xs text-space-dim leading-relaxed whitespace-pre-wrap">
              {job.description || 'No description available.'}
            </p>
          </details>
        </div>
      )}

      {contentTab === 'score' && (
        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-end gap-1">
            <HelpIcon text="Calls the LLM to rate how well this job matches your profile. Consumes a small amount of API credit per job." />
            <GatedButton
              action="score"
              onClick={handleAction}
              disabled={actionLoading || !promptOk}
              title={promptMissingTitle || undefined}
              className="px-3 py-1 rounded text-xs font-semibold transition-colors bg-purple-600 hover:bg-purple-500 text-white disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {actionLoading ? '…' : !promptOk ? 'Prompt not set' : job.final_score != null ? 'Recalculate' : 'Calculate'}
            </GatedButton>
          </div>
          {actionError && <p className="text-xs text-red-400 break-words">{actionError}</p>}
          <ScoreView job={job} />
        </div>
      )}

      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-[#0f0f1a] border border-space-border rounded-xl w-[90%] max-w-sm p-5 flex flex-col gap-4 shadow-2xl">
            <div>
              <p className="text-sm font-semibold text-space-text">Delete job?</p>
              <p className="text-xs text-space-dim mt-1">
                <span className="text-space-text">{job.title || job.job_key}</span> will move to the Archive tab.
                You can restore it by changing its status. It will be permanently removed on next app launch.
              </p>
            </div>
            {deleteError && <p className="text-xs text-red-400">{deleteError}</p>}
            <div className="flex gap-2">
              <button
                onClick={handleDelete}
                disabled={deleting}
                className="flex-1 py-2 rounded-lg bg-red-600 hover:bg-red-500 disabled:opacity-50 text-white text-sm font-semibold transition-colors"
              >
                {deleting ? 'Deleting…' : 'Confirm'}
              </button>
              <button
                onClick={() => setConfirmDelete(false)}
                className="px-4 py-2 rounded-lg border border-space-border text-sm text-space-dim hover:text-space-text transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
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
            <div className="flex items-center gap-1">
              <button
                onClick={() => setExpandDoc(contentTab)}
                disabled={!(contentTab === 'resume' ? hasResume : hasCover)}
                title={(contentTab === 'resume' ? hasResume : hasCover) ? 'Open document editor' : 'Generate before editing'}
                aria-label="Edit document"
                className="px-2 py-1 rounded text-sm transition-colors border border-space-border text-space-dim hover:text-space-text disabled:opacity-40 disabled:cursor-not-allowed"
              >
                ✎
              </button>
              <HelpIcon text="Generates a tailored resume and cover letter for this job, rendered to PDF. Uses more credits than scoring." />
              <GatedButton
                action="generate"
                onClick={handleAction}
                disabled={actionLoading || !promptOk}
                title={promptMissingTitle || undefined}
                className="px-3 py-1 rounded text-xs font-semibold transition-colors bg-purple-600 hover:bg-purple-500 text-white disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {actionLoading ? '…' : !promptOk ? 'Prompt not set' : (contentTab === 'resume' ? hasResume : hasCover) ? 'Regenerate' : 'Generate'}
              </GatedButton>
            </div>
          </div>
          {actionError && <p className="text-xs text-red-400 break-words">{actionError}</p>}

          {/* Eval score chip */}
          {(() => {
            const evalScore = contentTab === 'resume' ? job.resume_eval_score : job.cover_eval_score
            const evalTurns = contentTab === 'resume' ? job.resume_eval_turns : job.cover_eval_turns
            if (evalScore == null) return null
            const hue = Math.round(evalScore * 120)
            return (
              <div className="flex items-center gap-2">
                <span
                  style={{ color: `hsl(${hue}, 75%, 55%)` }}
                  className="text-sm font-bold tabular-nums"
                >
                  {(evalScore * 10).toFixed(1)}/10
                </span>
                <span className="text-xs text-space-dim">
                  ({evalTurns} turn{evalTurns !== 1 ? 's' : ''})
                </span>
              </div>
            )
          })()}

          {artifactView === 'markdown' && (
            <MarkdownView
              url={contentTab === 'resume'
                ? `/api/jobs/${job.job_key}/resume/markdown?v=${resumeCacheKey}`
                : `/api/jobs/${job.job_key}/cover/markdown?v=${coverCacheKey}`}
            />
          )}
          {artifactView === 'pdf' && (
            <iframe
              src={contentTab === 'resume'
                ? `/api/jobs/${job.job_key}/resume?v=${resumeCacheKey}`
                : `/api/jobs/${job.job_key}/cover?v=${coverCacheKey}`}
              className="w-full h-[600px] rounded border border-space-border"
              title={contentTab === 'resume' ? 'Resume PDF' : 'Cover Letter PDF'}
            />
          )}

          {/* Refinement history */}
          {(() => {
            const evalLog = contentTab === 'resume' ? (job.resume_eval_log || []) : (job.cover_eval_log || [])
            if (!evalLog.length) return null
            return (
              <div className="flex flex-col gap-3 mt-1">
                <hr className="border-space-border" />
                <p className="text-xs font-semibold uppercase tracking-widest text-space-dim">Refinement History</p>
                {evalLog.map((entry, idx) => {
                  const hue = Math.round(entry.score * 120)
                  const turnUrl = `/api/jobs/${job.job_key}/${contentTab}/turn/${entry.turn}/markdown`
                  return (
                    <TurnEntry
                      key={idx}
                      entry={entry}
                      hue={hue}
                      turnUrl={turnUrl}
                      isLast={idx === evalLog.length - 1}
                      showDivider={idx < evalLog.length - 1}
                    />
                  )
                })}
              </div>
            )
          })()}
        </div>
      )}
      {showEditFields && (
        <EditFieldsModal job={job} onClose={() => setShowEditFields(false)} />
      )}
      {expandDoc && (
        <DocumentModal
          job={job}
          docType={expandDoc}
          processing={actionsInFlight.has(`${expandDoc}_refine`) || actionsInFlight.has(`${expandDoc}_eval`)}
          onClose={() => setExpandDoc(null)}
        />
      )}
    </div>
  )
}

// ─── User tab ─────────────────────────────────────────────────────────────────

const PROVIDERS = [
  {
    value: 'openrouter',
    label: 'OpenRouter',
    defaultModel: 'deepseek/deepseek-v4-flash',
    models: [
      'deepseek/deepseek-v4-flash',
      'openrouter/auto',
      'openrouter/auto:free',
      'anthropic/claude-3.5-sonnet',
      'openai/gpt-4o-mini',
      'meta-llama/llama-3.1-8b-instruct:free',
    ],
  },
  {
    value: 'anthropic',
    label: 'Anthropic',
    defaultModel: 'claude-sonnet-4-6',
    models: [
      'claude-opus-4-7',
      'claude-sonnet-4-6',
      'claude-haiku-4-5-20251001',
      'claude-3-7-sonnet-latest',
      'claude-3-5-haiku-latest',
    ],
  },
  {
    value: 'openai',
    label: 'OpenAI',
    defaultModel: 'gpt-4o-mini',
    models: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-3.5-turbo'],
  },
  {
    value: 'gemini',
    label: 'Gemini',
    defaultModel: 'gemini-1.5-flash',
    models: [
      'gemini-2.0-flash',
      'gemini-1.5-pro',
      'gemini-1.5-flash',
      'gemini-1.5-flash-8b',
    ],
  },
]

function ModelCombobox({ value, onChange, models }) {
  const [open, setOpen] = useState(false)
  const filtered = value
    ? models.filter((m) => m.toLowerCase().includes(value.toLowerCase()))
    : models

  return (
    <div className="relative">
      <input
        type="text"
        value={value}
        onChange={(e) => { onChange(e.target.value); setOpen(true) }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        placeholder="e.g. gpt-4o-mini"
        className={inputClass}
      />
      {open && filtered.length > 0 && (
        <ul className="absolute z-10 mt-1 w-full max-h-48 overflow-auto bg-white text-black border border-space-border rounded shadow-lg">
          {filtered.map((m) => (
            <li
              key={m}
              onMouseDown={(e) => { e.preventDefault(); onChange(m); setOpen(false) }}
              className="px-2 py-1 hover:bg-gray-200 cursor-pointer text-sm"
            >
              {m}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function CreateProfile({ onBack, onCreated }) {
  const [step, setStep] = useState(1)
  const [createdId, setCreatedId] = useState(null)

  // Step 1
  const [name, setName] = useState('')
  const [providerType, setProviderType] = useState('')
  const [model, setModel] = useState('')
  const providerDef = PROVIDERS.find((p) => p.value === providerType)
  const [apiKey, setApiKey] = useState('')
  const [savingStep1, setSavingStep1] = useState(false)
  const [error, setError] = useState(null)
  const [fieldErrors, setFieldErrors] = useState({})

  // Step 2
  const [file, setFile] = useState(null)
  const [parsing, setParsing] = useState(false)
  const [parseError, setParseError] = useState(null)

  const handleStep1 = async () => {
    const errs = {}
    if (!name.trim()) errs.name = true
    if (!providerType) errs.providerType = true
    if (!model.trim()) errs.model = true
    if (!apiKey.trim()) errs.apiKey = true
    if (Object.keys(errs).length > 0) {
      setFieldErrors(errs)
      setError('Please fill in the required fields')
      return
    }
    setFieldErrors({})
    setSavingStep1(true)
    setError(null)
    const trimmed = name.trim()
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
    const fe = (key) => fieldErrors[key] ? ' !border-red-500/50' : ''
    const clearFe = (key) => setFieldErrors((prev) => { const n = { ...prev }; delete n[key]; return n })

    return (
      <div className="flex flex-col gap-4">
        <div>
          <p className="text-xs text-space-dim mb-1">Step 1 of 2 — Profile shell</p>
          <p className="text-sm text-space-dim">
            A profile links your identity, work history, and LLM provider. The app uses it to score jobs and tailor your resume.{' '}
            <a
              href="/docs#setting-up-your-llm-provider"
              target="_blank"
              rel="noopener noreferrer"
              className="text-purple-400 hover:text-purple-300 transition-colors"
            >
              Getting Started guide →
            </a>
          </p>
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-xs text-space-dim">Profile Name <span className="text-red-400">*</span></label>
          <input
            className={inputClass + fe('name')}
            value={name}
            onChange={(e) => { setName(e.target.value); setError(null); clearFe('name') }}
            placeholder="e.g. Software Engineer"
          />
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-xs text-space-dim">LLM Provider <span className="text-red-400">*</span></label>
          <select
            className={inputClass + fe('providerType')}
            value={providerType}
            onChange={(e) => {
              const v = e.target.value
              setProviderType(v)
              const p = PROVIDERS.find((x) => x.value === v)
              if (p) setModel(p.defaultModel)
              clearFe('providerType')
              clearFe('model')
            }}
          >
            <option value="" className="text-black bg-white">— select —</option>
            {PROVIDERS.map((p) => (
              <option key={p.value} value={p.value} className="text-black bg-white">{p.label}</option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-xs text-space-dim flex items-center">Model <span className="text-red-400 ml-1">*</span><HelpIcon text="The default model for your LLM calls. Check your provider's docs for the full list of available models they offer." /></label>
          {providerDef ? (
            <ModelCombobox
              value={model}
              onChange={(v) => { setModel(v); clearFe('model') }}
              models={providerDef.models}
            />
          ) : (
            <input
              className={inputClass + fe('model')}
              value={model}
              onChange={(e) => { setModel(e.target.value); clearFe('model') }}
              placeholder="e.g. gpt-4o-mini"
            />
          )}
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-xs text-space-dim">API Key <span className="text-red-400">*</span></label>
          <input
            type="password"
            className={inputClass + fe('apiKey')}
            value={apiKey}
            onChange={(e) => { setApiKey(e.target.value); clearFe('apiKey') }}
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
        <HelpIcon text="Uploads your resume to the LLM and extracts structured fields (experience, education, skills) into your profile. You can edit anything afterward." />
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

// ─── Root ─────────────────────────────────────────────────────────────────────

const TABS = ['User', 'Preview']

export default function Settings({ selectedJob, activeTab, onTabChange, promptStatus = {}, jobActionsInFlight = new Set(), onJobDeleted, onSkillFilter, activeSkill }) {
  const [view, setView] = useState('main') // 'main' | 'createProfile' | 'profileDetail'
  const [detailProfileId, setDetailProfileId] = useState(null)

  // Wizard "Manual Entry → Try it out" opens the active profile's editor directly.
  useEffect(() => {
    const handler = () => {
      getProfiles()
        .then(({ profiles, active_id }) => {
          const id = active_id ?? profiles?.[0]?.id
          if (id == null) return
          setDetailProfileId(id)
          setView('profileDetail')
        })
        .catch(() => {})
    }
    window.addEventListener('auto-apply:edit-profile', handler)
    return () => window.removeEventListener('auto-apply:edit-profile', handler)
  }, [])

  const isPreviewDisabled = selectedJob === null

  // Selecting a job (App sets activeTab='Preview') must surface the Preview even
  // when the user is deep in a profile view — pop back to main so it renders.
  useEffect(() => {
    if (selectedJob) setView('main')
  }, [selectedJob?.job_key])

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
              <UserHome
                onSelect={(id) => { setDetailProfileId(id); setView('main') }}
                onCreateProfile={() => setView('createProfile')}
                onSkillFilter={onSkillFilter}
                activeSkill={activeSkill}
              />
            )}

            {view === 'main' && activeTab === 'Preview' && (
              <PreviewTab job={selectedJob} promptStatus={promptStatus} actionsInFlight={jobActionsInFlight} onJobDeleted={onJobDeleted} />
            )}
            {view === 'createProfile' && (
              <CreateProfile
                onBack={() => setView('main')}
                onCreated={() => setView('main')}
              />
            )}
          </motion.div>
        </AnimatePresence>
      </div>
      {detailProfileId != null && (
        <ProfileEditorModal onClose={() => setDetailProfileId(null)}>
          <ProfileDetailView
            profileId={detailProfileId}
            onDelete={() => setDetailProfileId(null)}
          />
        </ProfileEditorModal>
      )}
    </motion.div>
  )
}
