import { useState, useEffect } from 'react'
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

function IdentitySection({ data, onSave }) {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({})
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const openModal = () => {
    setForm({
      first_name: data.first_name || '',
      last_name: data.last_name || '',
      hero: data.hero || '',
      location: data.location || '',
      email: data.email || '',
      phone: data.phone || '',
      linkedin: data.linkedin || '',
      github: data.github || '',
      website: data.website || '',
    })
    setError(null)
    setOpen(true)
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      await onSave(form)
      setOpen(false)
    } catch {
      setError('Save failed')
    } finally {
      setSaving(false)
    }
  }

  const f = (label, key, type = 'text') => (
    <div className="flex flex-col gap-1">
      <label className="text-xs text-space-dim">{label}</label>
      <input
        type={type}
        className={inputClass}
        value={form[key] ?? ''}
        onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
      />
    </div>
  )

  const fullName = [data.first_name, data.last_name].filter(Boolean).join(' ')

  return (
    <>
      <AccordionSection title="Identity" editButton={<EditBtn onClick={openModal} />}>
        <div className="flex flex-col gap-1.5">
          {fullName && <p className="text-sm font-medium text-space-text">{fullName}</p>}
          {data.hero && <p className="text-xs text-space-dim italic">{data.hero}</p>}
          <Field label="Email" value={data.email} />
          <Field label="Phone" value={data.phone} />
          <Field label="Location" value={data.location} />
          {data.linkedin && <Field label="LinkedIn" value={data.linkedin} />}
          {data.github && <Field label="GitHub" value={data.github} />}
          {data.website && <Field label="Website" value={data.website} />}
          {!fullName && !data.email && <p className="text-xs text-space-dim">No identity info yet.</p>}
        </div>
      </AccordionSection>

      {open && (
        <ItemOverlay title="Edit Identity" onClose={() => setOpen(false)} onSave={handleSave} saving={saving} error={error}>
          <p className="text-xs font-semibold uppercase tracking-widest text-space-dim">Personal</p>
          {f('First Name', 'first_name')}
          {f('Last Name', 'last_name')}
          {f('Tagline / Hero', 'hero')}
          {f('Location', 'location')}
          <hr className="border-space-border" />
          <p className="text-xs font-semibold uppercase tracking-widest text-space-dim">Contact</p>
          {f('Email', 'email', 'email')}
          {f('Phone', 'phone', 'tel')}
          <hr className="border-space-border" />
          <p className="text-xs font-semibold uppercase tracking-widest text-space-dim">Socials</p>
          {f('LinkedIn URL', 'linkedin', 'url')}
          {f('GitHub URL', 'github', 'url')}
          {f('Website URL', 'website', 'url')}
        </ItemOverlay>
      )}
    </>
  )
}
function SkillsSection({ data, onSave }) {
  const [overlayOpen, setOverlayOpen] = useState(false)
  const [editingIndex, setEditingIndex] = useState(null)
  const [inputVal, setInputVal] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const skills = data.skills || []

  const openAdd = () => { setEditingIndex(null); setInputVal(''); setError(null); setOverlayOpen(true) }
  const openEdit = (i) => { setEditingIndex(i); setInputVal(skills[i]); setError(null); setOverlayOpen(true) }

  const handleSave = async () => {
    const val = inputVal.trim()
    if (!val) { setError('Skill cannot be empty'); return }
    let updated
    if (editingIndex === null) {
      if (skills.includes(val)) { setError('Skill already exists'); return }
      updated = [...skills, val]
    } else {
      updated = skills.map((s, i) => i === editingIndex ? val : s)
    }
    setSaving(true)
    try {
      await onSave({ skills: updated })
      setOverlayOpen(false)
    } catch {
      setError('Save failed')
    } finally {
      setSaving(false)
    }
  }

  const handleRemove = async (i) => {
    const updated = skills.filter((_, idx) => idx !== i)
    await onSave({ skills: updated })
  }

  return (
    <>
      <AccordionSection title="Skills">
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap gap-1.5">
            {skills.map((s, i) => (
              <div key={i} className="flex items-center gap-1 bg-white/5 border border-space-border rounded-full px-2.5 py-0.5">
                <button
                  onClick={() => openEdit(i)}
                  className="text-xs text-space-text hover:text-purple-400 transition-colors"
                >
                  {s}
                </button>
                <button
                  onClick={() => handleRemove(i)}
                  className="text-space-dim hover:text-red-400 text-xs leading-none transition-colors"
                >
                  ×
                </button>
              </div>
            ))}
          </div>
          {skills.length === 0 && <p className="text-xs text-space-dim">No skills added yet.</p>}
          <button
            onClick={openAdd}
            className="self-start text-xs text-space-dim hover:text-space-text border border-space-border hover:border-purple-500/50 rounded px-2 py-1 transition-colors"
          >
            + Add Skill
          </button>
        </div>
      </AccordionSection>

      {overlayOpen && (
        <ItemOverlay
          title={editingIndex === null ? 'Add Skill' : 'Edit Skill'}
          onClose={() => setOverlayOpen(false)}
          onSave={handleSave}
          saving={saving}
          error={error}
        >
          <div className="flex flex-col gap-1">
            <label className="text-xs text-space-dim">Skill</label>
            <input
              autoFocus
              className={inputClass}
              value={inputVal}
              onChange={e => setInputVal(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSave()}
              placeholder="e.g. Python"
            />
          </div>
        </ItemOverlay>
      )}
    </>
  )
}
const EMPTY_EXPERIENCE = { company: '', title: '', start: '', end: '', summary: '' }

function ExperienceSection({ data, onSave }) {
  const [overlayOpen, setOverlayOpen] = useState(false)
  const [editingIndex, setEditingIndex] = useState(null)
  const [form, setForm] = useState(EMPTY_EXPERIENCE)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const items = data.work_history || []

  const openAdd = () => { setEditingIndex(null); setForm(EMPTY_EXPERIENCE); setError(null); setOverlayOpen(true) }
  const openEdit = (i) => { setEditingIndex(i); setForm({ ...items[i] }); setError(null); setOverlayOpen(true) }

  const handleSave = async () => {
    if (!form.company.trim() || !form.title.trim()) { setError('Company and title are required'); return }
    const updated = editingIndex === null
      ? [...items, form]
      : items.map((item, i) => i === editingIndex ? form : item)
    setSaving(true)
    try {
      await onSave({ work_history: updated })
      setOverlayOpen(false)
    } catch {
      setError('Save failed')
    } finally {
      setSaving(false)
    }
  }

  const handleRemove = async (i) => {
    await onSave({ work_history: items.filter((_, idx) => idx !== i) })
  }

  const f = (label, key, multiline = false) => (
    <div className="flex flex-col gap-1">
      <label className="text-xs text-space-dim">{label}</label>
      {multiline
        ? <textarea rows={3} className={inputClass + ' resize-none'} value={form[key] ?? ''} onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))} />
        : <input className={inputClass} value={form[key] ?? ''} onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))} />
      }
    </div>
  )

  return (
    <>
      <AccordionSection title="Experience">
        <div className="flex flex-col gap-2">
          {items.map((item, i) => (
            <div key={i} className="flex items-start justify-between gap-2 rounded-lg px-3 py-2.5 bg-white/[0.03] border border-white/5">
              <div className="min-w-0">
                <p className="text-sm font-medium text-space-text truncate">{item.title}</p>
                <p className="text-xs text-space-dim">{item.company} · {item.start}–{item.end}</p>
              </div>
              <div className="flex gap-1 shrink-0">
                <EditBtn onClick={() => openEdit(i)} />
                <button onClick={() => handleRemove(i)} className="px-2 py-0.5 rounded text-xs text-space-dim border border-space-border hover:text-red-400 transition-colors">✕</button>
              </div>
            </div>
          ))}
          {items.length === 0 && <p className="text-xs text-space-dim">No experience added yet.</p>}
          <button onClick={openAdd} className="self-start text-xs text-space-dim hover:text-space-text border border-space-border hover:border-purple-500/50 rounded px-2 py-1 transition-colors">
            + Add Experience
          </button>
        </div>
      </AccordionSection>

      {overlayOpen && (
        <ItemOverlay
          title={editingIndex === null ? 'Add Experience' : 'Edit Experience'}
          onClose={() => setOverlayOpen(false)}
          onSave={handleSave}
          saving={saving}
          error={error}
        >
          {f('Company', 'company')}
          {f('Title', 'title')}
          {f('Start (e.g. 2022-01)', 'start')}
          {f('End (e.g. Present)', 'end')}
          {f('Summary', 'summary', true)}
        </ItemOverlay>
      )}
    </>
  )
}
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
