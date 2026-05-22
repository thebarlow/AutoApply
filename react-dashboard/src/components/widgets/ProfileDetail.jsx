import { useState, useEffect, useRef } from 'react'
import { getProfile, updateProfile } from '../../api'

// ─── Shared ────────────────────────────────────────────────────────────────────

export const inputClass =
  'w-full bg-white/5 border border-space-border rounded-lg px-3 py-2 text-sm text-space-text placeholder-space-dim focus:outline-none focus:border-purple-500 transition-colors'

const PROVIDER_TYPES = ['openrouter', 'anthropic', 'openai', 'gemini']

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

function AccordionSection({ title, editButton, children }) {
  const [open, setOpen] = useState(true)
  return (
    <div className="border border-space-border rounded-lg overflow-hidden">
      <div
        className="flex items-center justify-between px-3 py-2.5 bg-white/[0.03] cursor-pointer select-none"
        onClick={() => setOpen(o => !o)}
      >
        <span className="text-xs font-semibold uppercase tracking-widest text-space-dim">{title}</span>
        <div className="flex items-center gap-2" onClick={e => e.stopPropagation()}>
          {editButton}
          <span className="text-space-dim pointer-events-none">
            <ChevronDown open={open} />
          </span>
        </div>
      </div>
      {open && <div className="p-3">{children}</div>}
    </div>
  )
}

// ─── ItemOverlay ───────────────────────────────────────────────────────────────

function ItemOverlay({ title, onClose, onSave, saving, error, children }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-[#0f0f1a] border border-space-border rounded-xl w-[90%] max-w-md max-h-[80vh] flex flex-col shadow-2xl">
        <div className="flex items-center justify-between px-4 py-3 border-b border-space-border shrink-0">
          <span className="text-sm font-semibold text-space-text">{title}</span>
          <button onClick={onClose} className="text-space-dim hover:text-space-text text-lg leading-none">×</button>
        </div>
        <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-3">{children}</div>
        <div className="px-4 py-3 border-t border-space-border shrink-0 flex flex-col gap-2">
          {error && <p className="text-xs text-red-400">{error}</p>}
          <div className="flex gap-2">
            <button
              onClick={onSave}
              disabled={saving}
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
  )
}

function EditBtn({ onClick }) {
  return (
    <button
      onClick={onClick}
      className="px-2 py-0.5 rounded text-xs text-space-dim border border-space-border hover:text-space-text hover:border-purple-500/50 transition-colors"
    >
      Edit
    </button>
  )
}

function Field({ label, value }) {
  if (!value) return null
  return (
    <div>
      <p className="text-xs text-space-dim">{label}</p>
      <p className="text-xs text-space-text">{value}</p>
    </div>
  )
}

// ─── Placeholder section components (filled in subsequent tasks) ───────────────

function IdentitySection({ data, onSave }) { return null }
function SkillsSection({ data, onSave }) { return null }
function ExperienceSection({ data, onSave }) { return null }
function EducationSection({ data, onSave }) { return null }
function ProjectsSection({ data, onSave }) { return null }
function JobPrefsSection({ data, onSave }) { return null }
function PromptsSection({ data, onSave }) { return null }
function LlmSection({ profile, onSave }) { return null }

// ─── ProfileDetailView ─────────────────────────────────────────────────────────

const PROFILE_DATA_DEFAULTS = {
  first_name: '', last_name: '', hero: '', email: '', phone: '',
  location: '', linkedin: '', github: '', website: '',
  skills: [], work_history: [], education: [], projects: [],
  target_roles: [], target_salary_min: null, target_salary_max: null,
  prompt_scoring: '', prompt_resume: '', prompt_cover: '',
  prompt_extraction: '', prompt_intake: '',
}

export default function ProfileDetailView({ profileId }) {
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

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

  const handleSaveLlm = async ({ providerType, model, apiKey }) => {
    const newData = { ...profile.data, llm_provider_type: providerType, llm_model: model }
    const body = { name: profile.name, data: newData }
    if (apiKey) body.llm_api_key = apiKey
    await updateProfile(profileId, body)
    setProfile(p => ({ ...p, data: newData, llm_provider_type: providerType, llm_model: model }))
  }

  if (loading) return <p className="text-xs text-space-dim">Loading…</p>
  if (error) return <p className="text-xs text-red-400">{error}</p>

  const d = profile.data

  return (
    <div className="flex flex-col gap-3">
      <IdentitySection data={d} onSave={handleSave} />
      <SkillsSection data={d} onSave={handleSave} />
      <ExperienceSection data={d} onSave={handleSave} />
      <EducationSection data={d} onSave={handleSave} />
      <ProjectsSection data={d} onSave={handleSave} />
      <JobPrefsSection data={d} onSave={handleSave} />
      <PromptsSection data={d} onSave={handleSave} />
      <LlmSection profile={profile} onSave={handleSaveLlm} />
    </div>
  )
}
