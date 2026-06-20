import { useState, useEffect, useRef, useCallback } from 'react'
import { getProfile, updateProfile, resetProfile, getPrompt, putPrompt, resetPrompt } from '../../api'
import HelpIcon from '../shared/HelpIcon'
import ProfileTreeEditor from './profile-tree/ProfileTreeEditor'

// ─── Shared ────────────────────────────────────────────────────────────────────

export const inputClass =
  'w-full bg-white/5 border border-space-border rounded-lg px-3 py-2 text-sm text-space-text placeholder-space-dim focus:outline-none focus:border-purple-500 transition-colors'

// Close-on-Escape hook for modals. Active controls whether the listener is registered.
function useEscape(active, handler) {
  useEffect(() => {
    if (!active) return
    const onKey = (e) => { if (e.key === 'Escape') handler() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [active, handler])
}

function ChevronDown({ open }) {
  return (
    <svg
      width="12" height="12" viewBox="0 0 12 12" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
      style={{ transform: open ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 0.2s' }}
    >
      <path d="M2 4l4 4 4-4" />
    </svg>
  )
}

// ─── AccordionSection ──────────────────────────────────────────────────────────

function AccordionSection({ id, title, editButton, empty, children }) {
  const storageKey = id ? `profile-accordion:${id}` : null
  const [open, setOpen] = useState(() => {
    if (!storageKey) return false
    try {
      return sessionStorage.getItem(storageKey) === '1'
    } catch {
      return false
    }
  })

  const toggle = () => {
    setOpen(prev => {
      const next = !prev
      if (storageKey) {
        try { sessionStorage.setItem(storageKey, next ? '1' : '0') } catch {}
      }
      return next
    })
  }

  return (
    <div className="border border-space-border rounded-lg overflow-hidden">
      <div
        className="flex items-center justify-between px-3 py-2.5 bg-white/[0.03] cursor-pointer select-none"
        onClick={toggle}
      >
        <span className="text-xs font-semibold uppercase tracking-widest text-space-dim flex items-center gap-2">
          {title}
          {empty && (
            <span className="font-normal normal-case tracking-normal text-[10px] text-space-dim/50">
              [empty]
            </span>
          )}
        </span>
        <div className="flex items-center gap-2">
          {editButton && <span onClick={e => e.stopPropagation()}>{editButton}</span>}
          <span className="text-space-dim">
            <ChevronDown open={open} />
          </span>
        </div>
      </div>
      {open && <div className="p-3">{children}</div>}
    </div>
  )
}

// ─── Prompts constants ────────────────────────────────────────────────────────

const PROMPT_HELP = {
  scoring: 'Scores how well a job matches your profile. Returns a numeric score and reasoning used to prioritize or filter jobs.',
  resume: 'Generates a tailored resume for a specific job, emphasizing your most relevant experience and skills.',
  cover: 'Generates a tailored cover letter for a job using your profile and the job posting details.',
  extraction: 'Extracts structured fields (title, requirements, location, salary) from a raw job description before scoring or generation.',
  resume_parse: 'Parses your uploaded resume into structured profile fields (experience, education, skills, etc.).',
}

const USER_CHIPS = [
  { label: 'first name', token: '{user.first_name}' },
  { label: 'last name', token: '{user.last_name}' },
  { label: 'hero', token: '{user.hero}' },
  { label: 'skills', token: '{user.skills}' },
  { label: 'work history', token: '{user.work_history}' },
  { label: 'education', token: '{user.education}' },
  { label: 'projects', token: '{user.projects}' },
  { label: 'target roles', token: '{user.target_roles}' },
  { label: 'salary min', token: '{user.target_salary_min}' },
  { label: 'salary max', token: '{user.target_salary_max}' },
  { label: 'full profile', token: '{profile}' },
]

const JOB_CHIPS = [
  { label: 'title', token: '{job.title}' },
  { label: 'company', token: '{job.company}' },
  { label: 'location', token: '{job.location}' },
  { label: 'salary', token: '{job.salary}' },
  { label: 'description', token: '{job.description}' },
  { label: 'processed description', token: '{job.extracted_description}' },
  { label: 'full job', token: '{job}' },
]

function resolveTokenValue(token, data) {
  if (!data) return ''
  const raw = {
    '{user.first_name}': data.first_name || '',
    '{user.last_name}': data.last_name || '',
    '{user.hero}': data.hero || '',
    '{user.skills}': (data.skills || []).join(', '),
    '{user.work_history}': (data.work_history || []).map(e => `${e.title} at ${e.company}`).join(' · '),
    '{user.education}': (data.education || []).map(e => `${e.degree} ${e.field}, ${e.institution}`).join(' · '),
    '{user.projects}': (data.projects || []).map(e => e.name).join(', '),
    '{user.target_roles}': (data.target_roles || []).join(', '),
    '{user.target_salary_min}': data.target_salary_min != null ? `$${data.target_salary_min.toLocaleString()}` : '',
    '{user.target_salary_max}': data.target_salary_max != null ? `$${data.target_salary_max.toLocaleString()}` : '',
    '{profile}': (() => { try { return JSON.stringify(data) } catch { return '' } })(),
  }
  const v = raw[token] ?? ''
  return v.length > 220 ? v.slice(0, 220) + '…' : v
}

const PROMPT_TYPE_KEYS = ['scoring', 'resume', 'cover', 'extraction', 'resume_parse']

const PROMPT_TYPE_LABELS = {
  scoring: 'Scoring',
  resume: 'Resume Generation',
  cover: 'Cover Letter Generation',
  extraction: 'Description Processing',
  resume_parse: 'Resume Parsing',
}

function PromptModal({ typeKey, profileId, profileData, defaultModel, onClose, onSaved }) {
  const label = PROMPT_TYPE_LABELS[typeKey]

  const [content, setContent] = useState('')
  const [model, setModel] = useState('')
  const [isDefault, setIsDefault] = useState(true)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [resetting, setResetting] = useState(false)
  const [saveError, setSaveError] = useState(null)
  const [popOut, setPopOut] = useState(false)
  const textareaRef = useRef(null)

  useEscape(popOut, () => setPopOut(false))
  useEscape(!popOut, onClose)

  // Load slot on mount
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    getPrompt(profileId, typeKey)
      .then(({ content: c, model: m, is_default: d }) => {
        if (cancelled) return
        setContent(c)
        setModel(m || '')
        setIsDefault(d)
      })
      .catch(() => { if (!cancelled) setSaveError('Failed to load prompt') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [profileId, typeKey])

  const handleDrop = useCallback((e) => {
    e.preventDefault()
    const token = e.dataTransfer.getData('text/plain')
    if (!token || !textareaRef.current) return
    const ta = textareaRef.current
    let offset = ta.selectionStart ?? 0
    if (document.caretPositionFromPoint) {
      const pos = document.caretPositionFromPoint(e.clientX, e.clientY)
      if (pos && pos.offsetNode === ta) offset = pos.offset
    }
    const before = content.slice(0, offset)
    const after = content.slice(offset)
    setContent(before + token + after)
    requestAnimationFrame(() => {
      ta.focus()
      ta.setSelectionRange(offset + token.length, offset + token.length)
    })
  }, [content])

  const handleDragOver = (e) => { e.preventDefault() }

  const handleSave = async () => {
    setSaving(true)
    setSaveError(null)
    try {
      const res = await putPrompt(profileId, typeKey, { content, model })
      onSaved(typeKey)
      window.dispatchEvent(new CustomEvent('auto-apply:prompt-status-stale'))
      onClose()
    } catch {
      setSaveError('Save failed')
    } finally {
      setSaving(false)
    }
  }

  const handleReset = async () => {
    setResetting(true)
    setSaveError(null)
    try {
      const res = await resetPrompt(profileId, typeKey)
      setContent(res.content)
      setModel(res.model || '')
      setIsDefault(res.is_default)
      window.dispatchEvent(new CustomEvent('auto-apply:prompt-status-stale'))
    } catch {
      setSaveError('Reset failed')
    } finally {
      setResetting(false)
    }
  }

  const renderChipTray = () => (
    <div className="flex flex-col gap-2">
      <label className="text-xs font-semibold uppercase tracking-widest text-space-dim">Insert Variable<HelpIcon text="Use placeholders like {job_description}, {resume}, {company_name} — they're substituted with actual job/profile data at generation time." /></label>
      <div className="flex flex-col gap-1.5">
        <p className="text-xs text-space-dim">User</p>
        <div className="flex flex-wrap gap-1.5">
          {USER_CHIPS.map(({ label: l, token }) => {
            const tipValue = resolveTokenValue(token, profileData)
            return (
              <div key={token} className="relative group">
                <div
                  draggable
                  onDragStart={(e) => e.dataTransfer.setData('text/plain', token)}
                  className="px-2 py-0.5 rounded-full border border-purple-500/40 bg-purple-500/10 text-xs text-purple-300 cursor-grab active:cursor-grabbing select-none"
                >
                  {l}
                </div>
                <div className="absolute bottom-full left-0 mb-1.5 z-50 w-56 bg-[#12121f] border border-space-border rounded-lg px-2.5 py-2 shadow-xl pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity duration-100">
                  <p className="text-[10px] font-mono break-all text-space-text leading-relaxed">
                    {tipValue || <span className="italic text-space-dim/50">empty</span>}
                  </p>
                </div>
              </div>
            )
          })}
        </div>
        <p className="text-xs text-space-dim mt-1">Job</p>
        <div className="flex flex-wrap gap-1.5">
          {JOB_CHIPS.map(({ label: l, token }) => (
            <div
              key={token}
              draggable
              onDragStart={(e) => e.dataTransfer.setData('text/plain', token)}
              className="px-2 py-0.5 rounded-full border border-blue-500/40 bg-blue-500/10 text-xs text-blue-300 cursor-grab active:cursor-grabbing select-none"
            >
              {l}
            </div>
          ))}
        </div>
      </div>
    </div>
  )

  const renderEditor = (extraTextareaClass = '') => {
    if (loading) return <p className="text-xs text-space-dim">Loading…</p>
    return (
      <textarea
        ref={textareaRef}
        rows={14}
        className={inputClass + ' resize-y font-mono text-xs ' + extraTextareaClass}
        value={content}
        onChange={(e) => setContent(e.target.value)}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
      />
    )
  }

  return (
    <>
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
        <div className="bg-[#0f0f1a] border border-space-border rounded-xl w-[90%] max-w-2xl max-h-[90vh] flex flex-col shadow-2xl">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-space-border shrink-0">
            <span className="text-sm font-semibold text-space-text">{label}</span>
            <button onClick={onClose} className="text-space-dim hover:text-space-text text-lg leading-none">×</button>
          </div>

          <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-4">
            {/* Model */}
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-semibold uppercase tracking-widest text-space-dim">Model</label>
              <input
                className={inputClass}
                value={model}
                onChange={(e) => setModel(e.target.value)}
                placeholder={defaultModel || 'e.g. gpt-4o-mini (leave blank to use profile default)'}
              />
            </div>

            {/* Chip tray (hidden while pop-out is open) */}
            {!popOut && renderChipTray()}

            {/* Editor (hidden while pop-out is open) */}
            {!popOut && (
              <div className="flex flex-col gap-1.5 flex-1">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-semibold uppercase tracking-widest text-space-dim">Prompt Text</label>
                  <button
                    type="button"
                    onClick={() => setPopOut(true)}
                    title="Open full-viewport editor"
                    className="text-space-dim hover:text-space-text p-1 rounded hover:bg-white/5 transition-colors"
                  >
                    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M10 2h4v4" />
                      <path d="M14 2L8.5 7.5" />
                      <path d="M6 14H2v-4" />
                      <path d="M2 14l5.5-5.5" />
                    </svg>
                  </button>
                </div>
                {renderEditor()}
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="px-4 py-3 border-t border-space-border shrink-0 flex flex-col gap-2">
            {saveError && <p className="text-xs text-red-400">{saveError}</p>}
            <div className="flex gap-2">
              <button
                onClick={handleReset}
                disabled={saving || resetting || loading || isDefault}
                title={isDefault ? 'Already using the default prompt' : 'Reset to default prompt'}
                className="px-3 py-2 rounded-lg border border-space-border text-xs text-space-dim hover:text-space-text disabled:opacity-50 transition-colors shrink-0"
              >
                {resetting ? 'Resetting…' : 'Reset to default'}
              </button>
              <button
                onClick={handleSave}
                disabled={saving || resetting || loading}
                className="flex-1 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white text-sm font-semibold transition-colors"
              >
                {saving ? 'Saving…' : 'Save'}
              </button>
              <button
                onClick={onClose}
                className="px-4 py-2 rounded-lg border border-space-border text-sm text-space-dim hover:text-space-text transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      </div>
      {popOut && (
        <div className="fixed inset-0 z-[60] flex flex-col bg-[#0a0a14]">
          <div className="flex items-center justify-between px-4 py-3 border-b border-space-border shrink-0">
            <span className="text-sm font-semibold text-space-text">{label} — Full Editor</span>
            <button
              onClick={() => setPopOut(false)}
              className="text-space-dim hover:text-space-text text-lg leading-none"
              title="Close full editor"
            >
              ×
            </button>
          </div>
          <div className="flex-1 flex flex-col gap-3 p-4 min-h-0">
            {renderChipTray()}
            <div className="flex flex-col gap-1.5 flex-1 min-h-0">
              <label className="text-xs font-semibold uppercase tracking-widest text-space-dim">Prompt Text</label>
              {renderEditor('flex-1 min-h-0')}
            </div>
          </div>
        </div>
      )}
    </>
  )
}

const REFINEMENT_EVAL_CHIPS = [
  { label: 'current doc', token: '{current_document}' },
]
const REFINEMENT_REFINE_CHIPS = [
  { label: 'current doc', token: '{current_document}' },
  { label: 'critique', token: '{critique}' },
]

function RefinementPromptModal({ docType, profileId, profileName, profileData, defaultModel, onClose, onSaved }) {
  const label = docType === 'resume' ? 'Resume Refinement' : 'Cover Letter Refinement'

  const [activeTab, setActiveTab] = useState('evaluator')
  const [maxTurns, setMaxTurns] = useState(profileData[`${docType}_refine_max_turns`] ?? 1)
  const [passScore, setPassScore] = useState(profileData[`${docType}_refine_pass_score`] ?? 0.80)

  // Evaluator slot state
  const [evalContent, setEvalContent] = useState('')
  const [evalModel, setEvalModel] = useState('')
  const [evalIsDefault, setEvalIsDefault] = useState(true)
  const [evalLoading, setEvalLoading] = useState(true)
  const evalTextareaRef = useRef(null)

  // Rewriter slot state
  const [refineContent, setRefineContent] = useState('')
  const [refineModel, setRefineModel] = useState('')
  const [refineIsDefault, setRefineIsDefault] = useState(true)
  const [refineLoading, setRefineLoading] = useState(true)
  const refineTextareaRef = useRef(null)

  // Shared state
  const [saving, setSaving] = useState(false)
  const [resetting, setResetting] = useState(false)
  const [saveError, setSaveError] = useState(null)
  const [popOut, setPopOut] = useState(false)

  const isEval = activeTab === 'evaluator'
  const currentContent = isEval ? evalContent : refineContent
  const setCurrentContent = isEval ? setEvalContent : setRefineContent
  const currentModel = isEval ? evalModel : refineModel
  const setCurrentModel = isEval ? setEvalModel : setRefineModel
  const currentIsDefault = isEval ? evalIsDefault : refineIsDefault
  const currentLoading = isEval ? evalLoading : refineLoading
  const currentTextareaRef = isEval ? evalTextareaRef : refineTextareaRef
  const currentTypeKey = isEval ? `${docType}_eval` : `${docType}_refine`
  const extraChips = isEval ? REFINEMENT_EVAL_CHIPS : REFINEMENT_REFINE_CHIPS

  useEscape(!popOut, onClose)
  useEscape(popOut, () => setPopOut(false))

  // Load both slots on mount
  useEffect(() => {
    let cancelled = false
    const evalKey = `${docType}_eval`
    const refineKey = `${docType}_refine`
    getPrompt(profileId, evalKey)
      .then(({ content: c, model: m, is_default: d }) => {
        if (cancelled) return
        setEvalContent(c); setEvalModel(m || ''); setEvalIsDefault(d)
      })
      .catch(() => {})
      .finally(() => { if (!cancelled) setEvalLoading(false) })
    getPrompt(profileId, refineKey)
      .then(({ content: c, model: m, is_default: d }) => {
        if (cancelled) return
        setRefineContent(c); setRefineModel(m || ''); setRefineIsDefault(d)
      })
      .catch(() => {})
      .finally(() => { if (!cancelled) setRefineLoading(false) })
    return () => { cancelled = true }
  }, [profileId, docType])

  const handleDrop = useCallback((e) => {
    e.preventDefault()
    const token = e.dataTransfer.getData('text/plain')
    if (!token || !currentTextareaRef.current) return
    const ta = currentTextareaRef.current
    const offset = ta.selectionStart ?? 0
    const before = currentContent.slice(0, offset)
    const after = currentContent.slice(offset)
    setCurrentContent(before + token + after)
    requestAnimationFrame(() => {
      ta.focus()
      ta.setSelectionRange(offset + token.length, offset + token.length)
    })
  }, [currentContent, currentTextareaRef, setCurrentContent])

  const handleDragOver = (e) => e.preventDefault()

  const handleSave = async () => {
    setSaving(true); setSaveError(null)
    try {
      // Save both prompt slots
      const [evalRes, refineRes] = await Promise.all([
        putPrompt(profileId, `${docType}_eval`, { content: evalContent, model: evalModel }),
        putPrompt(profileId, `${docType}_refine`, { content: refineContent, model: refineModel }),
      ])
      setEvalContent(evalRes.content); setEvalModel(evalRes.model || ''); setEvalIsDefault(evalRes.is_default)
      setRefineContent(refineRes.content); setRefineModel(refineRes.model || ''); setRefineIsDefault(refineRes.is_default)
      // Save max_turns / pass_score to profile data
      const newData = {
        ...profileData,
        [`${docType}_refine_max_turns`]: Number(maxTurns),
        [`${docType}_refine_pass_score`]: Number(passScore),
      }
      await updateProfile(profileId, { name: profileName || '', data: newData })
      onSaved(newData)
      window.dispatchEvent(new CustomEvent('auto-apply:prompt-status-stale'))
      onClose()
    } catch { setSaveError('Save failed') }
    finally { setSaving(false) }
  }

  const handleReset = async () => {
    setResetting(true); setSaveError(null)
    try {
      const res = await resetPrompt(profileId, currentTypeKey)
      if (isEval) {
        setEvalContent(res.content); setEvalModel(res.model || ''); setEvalIsDefault(res.is_default)
      } else {
        setRefineContent(res.content); setRefineModel(res.model || ''); setRefineIsDefault(res.is_default)
      }
      window.dispatchEvent(new CustomEvent('auto-apply:prompt-status-stale'))
    } catch { setSaveError('Reset failed') }
    finally { setResetting(false) }
  }

  const renderEditor = (extraClass = '') => {
    if (currentLoading) return <p className="text-xs text-space-dim">Loading…</p>
    return (
      <textarea
        ref={currentTextareaRef}
        rows={12}
        className={inputClass + ' resize-y font-mono text-xs ' + extraClass}
        value={currentContent}
        onChange={e => setCurrentContent(e.target.value)}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
      />
    )
  }

  const renderChipTray = () => (
    <div className="flex flex-col gap-2">
      <label className="text-xs font-semibold uppercase tracking-widest text-space-dim">Insert Variable</label>
      <div className="flex flex-col gap-1.5">
        <p className="text-xs text-space-dim">User</p>
        <div className="flex flex-wrap gap-1.5">
          {USER_CHIPS.map(({ label: l, token }) => (
            <div key={token} draggable onDragStart={e => e.dataTransfer.setData('text/plain', token)}
              className="px-2 py-0.5 rounded-full border border-purple-500/40 bg-purple-500/10 text-xs text-purple-300 cursor-grab select-none">
              {l}
            </div>
          ))}
        </div>
        <p className="text-xs text-space-dim mt-1">Job</p>
        <div className="flex flex-wrap gap-1.5">
          {JOB_CHIPS.map(({ label: l, token }) => (
            <div key={token} draggable onDragStart={e => e.dataTransfer.setData('text/plain', token)}
              className="px-2 py-0.5 rounded-full border border-blue-500/40 bg-blue-500/10 text-xs text-blue-300 cursor-grab select-none">
              {l}
            </div>
          ))}
        </div>
        <p className="text-xs text-space-dim mt-1">Refinement</p>
        <div className="flex flex-wrap gap-1.5">
          {extraChips.map(({ label: l, token }) => (
            <div key={token} draggable onDragStart={e => e.dataTransfer.setData('text/plain', token)}
              className="px-2 py-0.5 rounded-full border border-emerald-500/40 bg-emerald-500/10 text-xs text-emerald-300 cursor-grab select-none">
              {l}
            </div>
          ))}
        </div>
      </div>
    </div>
  )

  const renderTabContent = () => (
    <div className="flex flex-col gap-4">
      {/* Model */}
      <div className="flex flex-col gap-1.5">
        <label className="text-xs font-semibold uppercase tracking-widest text-space-dim">Model</label>
        <input className={inputClass} value={currentModel} onChange={e => setCurrentModel(e.target.value)}
          placeholder={defaultModel || 'e.g. gpt-4o-mini (leave blank for profile default)'} />
      </div>
      {/* Chip tray + editor (hidden when popped out) */}
      {!popOut && renderChipTray()}
      {!popOut && (
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center justify-between">
            <label className="text-xs font-semibold uppercase tracking-widest text-space-dim">Prompt Text</label>
            <button type="button" onClick={() => setPopOut(true)} className="text-space-dim hover:text-space-text p-1 rounded hover:bg-white/5 transition-colors">
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                <path d="M10 2h4v4" /><path d="M14 2L8.5 7.5" /><path d="M6 14H2v-4" /><path d="M2 14l5.5-5.5" />
              </svg>
            </button>
          </div>
          {renderEditor()}
        </div>
      )}
    </div>
  )

  return (
    <>
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
        <div className="bg-[#0f0f1a] border border-space-border rounded-xl w-[90%] max-w-2xl max-h-[90vh] flex flex-col shadow-2xl">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-space-border shrink-0">
            <span className="text-sm font-semibold text-space-text">{label}</span>
            <button onClick={onClose} className="text-space-dim hover:text-space-text text-lg leading-none">×</button>
          </div>

          {/* Config row */}
          <div className="flex items-center gap-4 px-4 py-2 border-b border-space-border shrink-0">
            <div className="flex items-center gap-2">
              <label className="text-xs text-space-dim whitespace-nowrap">Max Turns</label>
              <input type="number" min="1" max="10" className="w-16 bg-white/5 border border-space-border rounded px-2 py-1 text-xs text-space-text focus:outline-none focus:border-purple-500"
                value={maxTurns} onChange={e => setMaxTurns(Math.max(1, Math.min(10, Number(e.target.value))))} />
            </div>
            <div className="flex items-center gap-2">
              <label className="text-xs text-space-dim whitespace-nowrap">Pass Score</label>
              <input type="number" min="0" max="1" step="0.05" className="w-20 bg-white/5 border border-space-border rounded px-2 py-1 text-xs text-space-text focus:outline-none focus:border-purple-500"
                value={passScore} onChange={e => setPassScore(Math.max(0, Math.min(1, Number(e.target.value))))} />
              <span className="text-xs text-space-dim">(0–1)</span>
            </div>
          </div>

          {/* Tab bar */}
          <div className="flex border-b border-space-border shrink-0">
            {[['evaluator', 'Evaluator'], ['rewriter', 'Rewriter']].map(([key, lbl]) => (
              <button key={key} onClick={() => { setActiveTab(key); setPopOut(false) }}
                className={`flex-1 py-2 text-xs font-semibold uppercase tracking-widest transition-colors ${activeTab === key ? 'text-purple-400 border-b-2 border-purple-400 bg-white/5' : 'text-space-dim hover:text-space-text'}`}>
                {lbl}
              </button>
            ))}
          </div>

          {/* Tab content */}
          <div className="flex-1 overflow-y-auto p-4">
            {renderTabContent()}
          </div>

          {/* Footer */}
          <div className="px-4 py-3 border-t border-space-border shrink-0 flex flex-col gap-2">
            {saveError && <p className="text-xs text-red-400">{saveError}</p>}
            <div className="flex gap-2">
              <button
                onClick={handleReset}
                disabled={saving || resetting || currentLoading || currentIsDefault}
                title={currentIsDefault ? 'Already using the default' : 'Reset this slot to default'}
                className="px-3 py-2 rounded-lg border border-space-border text-xs text-space-dim hover:text-space-text disabled:opacity-50 shrink-0"
              >
                {resetting ? 'Resetting…' : 'Reset to default'}
              </button>
              {/* block save until both slots loaded — save writes eval+refine together */}
              <button onClick={handleSave} disabled={saving || resetting || evalLoading || refineLoading}
                className="flex-1 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white text-sm font-semibold transition-colors">
                {saving ? 'Saving…' : 'Save'}
              </button>
              <button onClick={onClose} className="px-4 py-2 rounded-lg border border-space-border text-sm text-space-dim hover:text-space-text transition-colors">
                Cancel
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Pop-out full editor */}
      {popOut && (
        <div className="fixed inset-0 z-[60] flex flex-col bg-[#0a0a14]">
          <div className="flex items-center justify-between px-4 py-3 border-b border-space-border shrink-0">
            <span className="text-sm font-semibold text-space-text">
              {label} — {activeTab === 'evaluator' ? 'Evaluator' : 'Rewriter'} — Full Editor
            </span>
            <button onClick={() => setPopOut(false)} className="text-space-dim hover:text-space-text text-lg leading-none">×</button>
          </div>
          <div className="flex-1 flex flex-col gap-3 p-4 min-h-0">
            {renderChipTray()}
            <div className="flex flex-col gap-1.5 flex-1 min-h-0">
              <label className="text-xs font-semibold uppercase tracking-widest text-space-dim">Prompt Text</label>
              {renderEditor('flex-1 min-h-0')}
            </div>
          </div>
        </div>
      )}
    </>
  )
}

function PromptsSection({ data, profileId, profileName, defaultModel, onSave }) {
  const [openModal, setOpenModal] = useState(null)           // typeKey string | null
  const [openRefinement, setOpenRefinement] = useState(null) // 'resume' | 'cover' | null
  const [togglingRefine, setTogglingRefine] = useState(null) // 'resume' | 'cover' | null

  const handleSaved = (typeKey) => {
    // Prompt content/model live in the prompts table now — nothing to patch in
    // profile.data. PromptModal dispatches 'auto-apply:prompt-status-stale' itself
    // to refresh the status indicators.
  }

  const handleRefinementSaved = (docType, newData) => {
    // Persist max_turns / pass_score from RefinementPromptModal into profile data.
    onSave({
      [`${docType}_refine_max_turns`]: newData[`${docType}_refine_max_turns`],
      [`${docType}_refine_pass_score`]: newData[`${docType}_refine_pass_score`],
    })
  }

  const handleToggleRefinement = async (e, docType) => {
    e.stopPropagation()
    if (togglingRefine) return
    setTogglingRefine(docType)
    const field = `${docType}_refine_enabled`
    const current = data[field] !== false // default true
    try {
      await onSave({ [field]: !current })
    } finally {
      setTogglingRefine(null)
    }
  }

  const truncate = (s, n = 22) => s && s.length > n ? s.slice(0, n) + '…' : s

  return (
    <>
      <AccordionSection id="prompts" title="Prompts">
        <div className="flex flex-col gap-2">

          {/* ── Standard generation prompt cards ── */}
          {PROMPT_TYPE_KEYS.map((typeKey) => {
            // Use _configured and _model flags returned by getProfile (DB-backed)
            const configured = Boolean(data[`prompt_${typeKey}_configured`])
            const model = data[`prompt_${typeKey}_model`] || ''

            // After resume, inject resume-refinement card; after cover, inject cover-refinement card
            const refinementDocType = typeKey === 'resume' ? 'resume' : typeKey === 'cover' ? 'cover' : null

            return (
              <div key={typeKey} className="flex flex-col gap-1.5">
                {/* Generation card */}
                <button
                  onClick={() => setOpenModal(typeKey)}
                  className="flex items-start justify-between gap-3 rounded-lg px-3 py-2.5 bg-white/[0.03] border border-white/5 hover:border-purple-500/30 transition-colors text-left w-full"
                >
                  <div className="flex flex-col gap-0.5 min-w-0">
                    <span className="text-xs font-semibold text-space-text flex items-center gap-1">
                      {PROMPT_TYPE_LABELS[typeKey]}
                      <span onClick={e => e.stopPropagation()}>
                        <HelpIcon text={PROMPT_HELP[typeKey] || 'A prompt template used by the LLM.'} />
                      </span>
                    </span>
                    {model
                      ? <span className="text-xs text-purple-400/70 truncate">{truncate(model)}</span>
                      : defaultModel && <span className="text-xs text-space-dim/50 truncate">{truncate(defaultModel)} (default)</span>
                    }
                  </div>
                  <span className={`shrink-0 text-xs font-medium mt-0.5 ${configured ? 'text-green-400' : 'text-space-dim/40'}`}>
                    {configured ? 'Custom' : 'Default'}
                  </span>
                </button>

                {/* Refinement card — shown only after resume and cover */}
                {refinementDocType && (() => {
                  const evalConfigured = Boolean(data[`prompt_${refinementDocType}_eval_configured`])
                  const refineConfigured = Boolean(data[`prompt_${refinementDocType}_refine_configured`])
                  const evalModel = data[`prompt_${refinementDocType}_eval_model`] || ''
                  const refineModel = data[`prompt_${refinementDocType}_refine_model`] || ''
                  const enabled = data[`${refinementDocType}_refine_enabled`] !== false
                  const isToggling = togglingRefine === refinementDocType
                  return (
                    <button
                      onClick={() => setOpenRefinement(refinementDocType)}
                      className="flex items-start justify-between gap-3 rounded-lg px-3 py-2.5 bg-white/[0.02] border border-white/5 hover:border-emerald-500/20 transition-colors text-left w-full ml-3"
                    >
                      <div className="flex flex-col gap-0.5 min-w-0 flex-1">
                        <span className="text-xs font-semibold text-space-text/80">
                          {refinementDocType === 'resume' ? 'Resume Refinement' : 'Cover Letter Refinement'}
                        </span>
                        <span className="text-xs text-space-dim/70 truncate">
                          Eval: <span className={evalConfigured ? 'text-green-400/70' : 'text-space-dim/40'}>{evalConfigured ? 'Custom' : 'Default'}</span>
                          {evalModel ? <span className="text-purple-400/50"> · {truncate(evalModel, 16)}</span> : null}
                        </span>
                        <span className="text-xs text-space-dim/70 truncate">
                          Rewrite: <span className={refineConfigured ? 'text-green-400/70' : 'text-space-dim/40'}>{refineConfigured ? 'Custom' : 'Default'}</span>
                          {refineModel ? <span className="text-purple-400/50"> · {truncate(refineModel, 16)}</span> : null}
                        </span>
                      </div>
                      <button
                        onClick={e => handleToggleRefinement(e, refinementDocType)}
                        disabled={isToggling}
                        title={enabled ? 'Disable refinement' : 'Enable refinement'}
                        className={`shrink-0 text-xs font-medium mt-0.5 px-2 py-0.5 rounded border transition-colors disabled:opacity-50
                          ${enabled
                            ? 'text-emerald-400 border-emerald-500/40 hover:bg-emerald-500/10'
                            : 'text-space-dim/40 border-space-border hover:text-space-dim hover:border-space-border/60'
                          }`}
                      >
                        {enabled ? '✓ On' : '✗ Off'}
                      </button>
                    </button>
                  )
                })()}
              </div>
            )
          })}
        </div>
      </AccordionSection>

      {openModal && (
        <PromptModal
          typeKey={openModal}
          profileId={profileId}
          profileData={data}
          defaultModel={defaultModel}
          onClose={() => setOpenModal(null)}
          onSaved={handleSaved}
        />
      )}

      {openRefinement && (
        <RefinementPromptModal
          docType={openRefinement}
          profileId={profileId}
          profileName={profileName}
          profileData={data}
          defaultModel={defaultModel}
          onClose={() => setOpenRefinement(null)}
          onSaved={(newData) => handleRefinementSaved(openRefinement, newData)}
        />
      )}
    </>
  )
}
// ─── ProfileDetailView ─────────────────────────────────────────────────────────

const PROFILE_DATA_DEFAULTS = {
  first_name: '', last_name: '', hero: '', email: '', phone: '',
  location: '', linkedin: '', github: '', website: '',
  skills: [], work_history: [], education: [], projects: [],
  target_roles: [], target_salary_min: null, target_salary_max: null,
}

export default function ProfileDetailView({ profileId, onDelete }) {
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [confirmReset, setConfirmReset] = useState(false)
  useEscape(confirmReset, () => setConfirmReset(false))
  const [resetting, setResetting] = useState(false)
  const [resetError, setResetError] = useState(null)
  const [resetPhrase, setResetPhrase] = useState('')
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    getProfile(profileId)
      .then(raw => setProfile({ ...raw, data: { ...PROFILE_DATA_DEFAULTS, ...raw.data } }))
      .catch(() => setError('Failed to load profile'))
      .finally(() => setLoading(false))
  }, [profileId])

  const handleSave = async (patch) => {
    const newData = { ...profile.data, ...patch }
    await updateProfile(profileId, { name: profile.name, data: newData })
    setProfile(p => ({ ...p, data: newData }))
  }

  const handleExportMaster = async () => {
    setExporting(true)
    setExportError(null)
    try {
      const res = await fetch('/api/profile/export-master', { method: 'POST' })
      if (!res.ok) throw new Error('Export failed')
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'master_resume.pdf'
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      console.error('Export master failed:', e)
      setExportError('Export failed. Please try again.')
    } finally {
      setExporting(false)
    }
  }

  const handleReset = async () => {
    setResetting(true)
    setResetError(null)
    try {
      await resetProfile(profileId)
      window.location.reload()
    } catch {
      setResetError('Reset failed')
      setResetting(false)
    }
  }

  if (loading) return <p className="text-xs text-space-dim">Loading…</p>
  if (error) return <p className="text-xs text-red-400">{error}</p>

  const d = profile.data

  return (
    <>
      <div className="flex flex-col gap-3">
        <ProfileTreeEditor profileId={profileId} />
        <PromptsSection
          data={d}
          profileId={profileId}
          profileName={profile.name}
          defaultModel={profile.llm_model || ''}
          onSave={handleSave}
        />

        <button
          onClick={handleExportMaster}
          disabled={exporting}
          className="w-full py-2 rounded-lg border border-purple-500/30 text-sm text-purple-400 hover:bg-purple-500/10 transition-colors mt-2 disabled:opacity-50"
        >
          {exporting ? 'Generating…' : 'Export Master'}
        </button>
        {exportError && <p className="text-xs text-red-400 mt-1">{exportError}</p>}
        <button
          onClick={() => { setResetError(null); setResetPhrase(''); setConfirmReset(true) }}
          className="w-full py-2 rounded-lg border border-red-500/30 text-sm text-red-400 hover:bg-red-500/10 transition-colors mt-2"
        >
          Reset Profile
        </button>
      </div>

      {confirmReset && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-[#0f0f1a] border border-space-border rounded-xl w-[90%] max-w-sm p-5 flex flex-col gap-4 shadow-2xl">
            <div>
              <p className="text-sm font-semibold text-space-text">Reset profile?</p>
              <p className="text-xs text-space-dim mt-1">
                This permanently clears your résumé data — contact info, skills, work
                history, education, projects, and your uploaded files. Your scraped jobs
                and any documents you've already generated are kept. You'll be taken back
                through résumé upload.
              </p>
              <p className="text-xs text-space-dim mt-2">
                Type <span className="text-space-text font-semibold">Reset my Profile</span> to confirm.
              </p>
            </div>
            <input
              type="text"
              value={resetPhrase}
              onChange={(e) => setResetPhrase(e.target.value)}
              placeholder="Reset my Profile"
              className="w-full bg-white/5 border border-space-border rounded-lg px-3 py-2 text-sm text-space-text placeholder-space-dim focus:outline-none focus:border-purple-500 transition-colors"
            />
            {resetError && <p className="text-xs text-red-400">{resetError}</p>}
            <div className="flex gap-2">
              <button
                onClick={handleReset}
                disabled={resetting || resetPhrase !== 'Reset my Profile'}
                className="flex-1 py-2 rounded-lg bg-red-600 hover:bg-red-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-semibold transition-colors"
              >
                {resetting ? 'Resetting…' : 'Reset Profile'}
              </button>
              <button
                onClick={() => setConfirmReset(false)}
                className="px-4 py-2 rounded-lg border border-space-border text-sm text-space-dim hover:text-space-text transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

