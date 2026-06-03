import { useState, useEffect, useRef, useCallback } from 'react'
import { getProfile, updateProfile, deleteProfile, listPrompts, getPromptFile, putPromptFile, createPromptFile, uploadPromptFile, getDefaultPrompt } from '../../api'
import { validateProvider } from '../../validation'
import HelpIcon from '../shared/HelpIcon'

// ─── Shared ────────────────────────────────────────────────────────────────────

export const inputClass =
  'w-full bg-white/5 border border-space-border rounded-lg px-3 py-2 text-sm text-space-text placeholder-space-dim focus:outline-none focus:border-purple-500 transition-colors'

const PROVIDER_TYPES = ['openrouter', 'anthropic', 'openai', 'gemini']

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

// ─── isSectionEmpty ────────────────────────────────────────────────────────────

function isSectionEmpty(section, d) {
  switch (section) {
    case "identity":
      return (
        !d.first_name && !d.last_name && !d.hero &&
        !d.email && !d.phone && !d.location &&
        !d.linkedin && !d.github && !d.website
      );
    case "skills":
      return !d.skills || d.skills.length === 0;
    case "experience":
      return !d.work_history || d.work_history.length === 0;
    case "education":
      return !d.education || d.education.length === 0;
    case "projects":
      return !d.projects || d.projects.length === 0;
    case "job-preferences": {
      const roles = d.target_roles;
      const hasRoles = Array.isArray(roles) ? roles.length > 0 : Boolean(roles);
      return !hasRoles && d.target_salary_min == null && d.target_salary_max == null;
    }
    default:
      return false;
  }
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

// ─── ItemOverlay ───────────────────────────────────────────────────────────────

function ItemOverlay({ title, onClose, onSave, saving, error, children }) {
  useEscape(true, onClose)
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

  const f = (label, key, type = 'text', multiline = false) => (
    <div className="flex flex-col gap-1">
      <label className="text-xs text-space-dim">{label}</label>
      {multiline
        ? <textarea rows={3} className={inputClass + ' resize-none'} value={form[key] ?? ''} onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))} />
        : <input type={type} className={inputClass} value={form[key] ?? ''} onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))} />
      }
    </div>
  )

  const fullName = [data.first_name, data.last_name].filter(Boolean).join(' ')

  return (
    <>
      <AccordionSection id="identity" title="Identity" editButton={<EditBtn onClick={openModal} />} empty={isSectionEmpty("identity", data)}>
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
          {f('Tagline / Hero', 'hero', 'text', true)}
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
      <AccordionSection id="skills" title="Skills" empty={isSectionEmpty("skills", data)}>
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
      <AccordionSection id="experience" title="Experience" empty={isSectionEmpty("experience", data)}>
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
const EMPTY_EDUCATION = { institution: '', degree: '', field: '', graduated: '', gpa: '' }

function EducationSection({ data, onSave }) {
  const [overlayOpen, setOverlayOpen] = useState(false)
  const [editingIndex, setEditingIndex] = useState(null)
  const [form, setForm] = useState(EMPTY_EDUCATION)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const items = data.education || []

  const openAdd = () => { setEditingIndex(null); setForm(EMPTY_EDUCATION); setError(null); setOverlayOpen(true) }
  const openEdit = (i) => { setEditingIndex(i); setForm({ ...items[i], gpa: String(items[i].gpa ?? '') }); setError(null); setOverlayOpen(true) }

  const handleSave = async () => {
    if (!form.institution.trim()) { setError('Institution is required'); return }
    const entry = { ...form, gpa: parseFloat(form.gpa) || 0 }
    const updated = editingIndex === null
      ? [...items, entry]
      : items.map((item, i) => i === editingIndex ? entry : item)
    setSaving(true)
    try {
      await onSave({ education: updated })
      setOverlayOpen(false)
    } catch {
      setError('Save failed')
    } finally {
      setSaving(false)
    }
  }

  const handleRemove = async (i) => {
    await onSave({ education: items.filter((_, idx) => idx !== i) })
  }

  const f = (label, key) => (
    <div className="flex flex-col gap-1">
      <label className="text-xs text-space-dim">{label}</label>
      <input className={inputClass} value={form[key] ?? ''} onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))} />
    </div>
  )

  return (
    <>
      <AccordionSection id="education" title="Education" empty={isSectionEmpty("education", data)}>
        <div className="flex flex-col gap-2">
          {items.map((item, i) => (
            <div key={i} className="flex items-start justify-between gap-2 rounded-lg px-3 py-2.5 bg-white/[0.03] border border-white/5">
              <div className="min-w-0">
                <p className="text-sm font-medium text-space-text truncate">{item.degree} in {item.field}</p>
                <p className="text-xs text-space-dim">{item.institution} · {item.graduated}{item.gpa ? ` · GPA ${item.gpa}` : ''}</p>
              </div>
              <div className="flex gap-1 shrink-0">
                <EditBtn onClick={() => openEdit(i)} />
                <button onClick={() => handleRemove(i)} className="px-2 py-0.5 rounded text-xs text-space-dim border border-space-border hover:text-red-400 transition-colors">✕</button>
              </div>
            </div>
          ))}
          {items.length === 0 && <p className="text-xs text-space-dim">No education added yet.</p>}
          <button onClick={openAdd} className="self-start text-xs text-space-dim hover:text-space-text border border-space-border hover:border-purple-500/50 rounded px-2 py-1 transition-colors">
            + Add Education
          </button>
        </div>
      </AccordionSection>

      {overlayOpen && (
        <ItemOverlay
          title={editingIndex === null ? 'Add Education' : 'Edit Education'}
          onClose={() => setOverlayOpen(false)}
          onSave={handleSave}
          saving={saving}
          error={error}
        >
          {f('Institution', 'institution')}
          {f('Degree (e.g. B.S.)', 'degree')}
          {f('Field of Study', 'field')}
          {f('Graduated (e.g. 2018)', 'graduated')}
          {f('GPA', 'gpa')}
        </ItemOverlay>
      )}
    </>
  )
}
const EMPTY_PROJECT = { name: '', description: '', url: '', technologies: [] }

function ProjectsSection({ data, onSave }) {
  const [overlayOpen, setOverlayOpen] = useState(false)
  const [editingIndex, setEditingIndex] = useState(null)
  const [form, setForm] = useState(EMPTY_PROJECT)
  const [techInput, setTechInput] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const items = data.projects || []

  const openAdd = () => {
    setEditingIndex(null); setForm(EMPTY_PROJECT)
    setTechInput(''); setError(null); setOverlayOpen(true)
  }
  const openEdit = (i) => {
    setEditingIndex(i)
    setForm({ ...items[i], technologies: [...(items[i].technologies || [])] })
    setTechInput((items[i].technologies || []).join(', '))
    setError(null); setOverlayOpen(true)
  }

  const handleSave = async () => {
    if (!form.name.trim()) { setError('Project name is required'); return }
    const technologies = techInput.split(',').map(t => t.trim()).filter(Boolean)
    const entry = { ...form, technologies }
    const updated = editingIndex === null
      ? [...items, entry]
      : items.map((item, i) => i === editingIndex ? entry : item)
    setSaving(true)
    try {
      await onSave({ projects: updated })
      setOverlayOpen(false)
    } catch {
      setError('Save failed')
    } finally {
      setSaving(false)
    }
  }

  const handleRemove = async (i) => {
    await onSave({ projects: items.filter((_, idx) => idx !== i) })
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
      <AccordionSection id="projects" title="Projects" empty={isSectionEmpty("projects", data)}>
        <div className="flex flex-col gap-2">
          {items.map((item, i) => (
            <div key={i} className="flex items-start justify-between gap-2 rounded-lg px-3 py-2.5 bg-white/[0.03] border border-white/5">
              <div className="min-w-0">
                <p className="text-sm font-medium text-space-text truncate">{item.name}</p>
                {item.technologies?.length > 0 && (
                  <p className="text-xs text-space-dim truncate">{item.technologies.join(', ')}</p>
                )}
              </div>
              <div className="flex gap-1 shrink-0">
                <EditBtn onClick={() => openEdit(i)} />
                <button onClick={() => handleRemove(i)} className="px-2 py-0.5 rounded text-xs text-space-dim border border-space-border hover:text-red-400 transition-colors">✕</button>
              </div>
            </div>
          ))}
          {items.length === 0 && <p className="text-xs text-space-dim">No projects added yet.</p>}
          <button onClick={openAdd} className="self-start text-xs text-space-dim hover:text-space-text border border-space-border hover:border-purple-500/50 rounded px-2 py-1 transition-colors">
            + Add Project
          </button>
        </div>
      </AccordionSection>

      {overlayOpen && (
        <ItemOverlay
          title={editingIndex === null ? 'Add Project' : 'Edit Project'}
          onClose={() => setOverlayOpen(false)}
          onSave={handleSave}
          saving={saving}
          error={error}
        >
          {f('Project Name', 'name')}
          {f('Description', 'description', true)}
          {f('URL', 'url')}
          <div className="flex flex-col gap-1">
            <label className="text-xs text-space-dim">Technologies (comma-separated)</label>
            <input
              className={inputClass}
              value={techInput}
              onChange={e => setTechInput(e.target.value)}
              placeholder="e.g. Python, React, Docker"
            />
          </div>
        </ItemOverlay>
      )}
    </>
  )
}
function JobPrefsSection({ data, onSave }) {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({})
  const [rolesInput, setRolesInput] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const openModal = () => {
    setForm({
      target_salary_min: data.target_salary_min ?? '',
      target_salary_max: data.target_salary_max ?? '',
    })
    setRolesInput((data.target_roles || []).join(', '))
    setError(null)
    setOpen(true)
  }

  const handleSave = async () => {
    const target_roles = rolesInput.split(',').map(r => r.trim()).filter(Boolean)
    const patch = {
      target_roles,
      target_salary_min: form.target_salary_min !== '' ? Number(form.target_salary_min) : null,
      target_salary_max: form.target_salary_max !== '' ? Number(form.target_salary_max) : null,
    }
    setSaving(true)
    try {
      await onSave(patch)
      setOpen(false)
    } catch {
      setError('Save failed')
    } finally {
      setSaving(false)
    }
  }

  const salaryStr = data.target_salary_min != null && data.target_salary_max != null
    ? `$${data.target_salary_min.toLocaleString()} – $${data.target_salary_max.toLocaleString()}`
    : data.target_salary_min != null ? `From $${data.target_salary_min.toLocaleString()}` : null

  return (
    <>
      <AccordionSection id="job-preferences" title="Job Preferences" editButton={<EditBtn onClick={openModal} />} empty={isSectionEmpty("job-preferences", data)}>
        <div className="flex flex-col gap-1.5">
          {(data.target_roles || []).length > 0 && (
            <Field label="Target Roles" value={data.target_roles.join(', ')} />
          )}
          {salaryStr && <Field label="Target Salary" value={salaryStr} />}
          {!(data.target_roles?.length) && !salaryStr && (
            <p className="text-xs text-space-dim">No preferences set yet.</p>
          )}
        </div>
      </AccordionSection>

      {open && (
        <ItemOverlay title="Job Preferences" onClose={() => setOpen(false)} onSave={handleSave} saving={saving} error={error}>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-space-dim">Target Roles (comma-separated)</label>
            <input
              className={inputClass}
              value={rolesInput}
              onChange={e => setRolesInput(e.target.value)}
              placeholder="e.g. Backend Engineer, Staff Engineer"
            />
          </div>
          <div className="flex gap-2">
            <div className="flex flex-col gap-1 flex-1">
              <label className="text-xs text-space-dim">Salary Min ($)</label>
              <input
                type="number"
                className={inputClass}
                value={form.target_salary_min ?? ''}
                onChange={e => setForm(f => ({ ...f, target_salary_min: e.target.value }))}
                placeholder="120000"
              />
            </div>
            <div className="flex flex-col gap-1 flex-1">
              <label className="text-xs text-space-dim">Salary Max ($)</label>
              <input
                type="number"
                className={inputClass}
                value={form.target_salary_max ?? ''}
                onChange={e => setForm(f => ({ ...f, target_salary_max: e.target.value }))}
                placeholder="160000"
              />
            </div>
          </div>
        </ItemOverlay>
      )}
    </>
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

function PromptModal({ typeKey, profileId, profileName, profileData, defaultModel, onClose, onSaved }) {
  const label = PROMPT_TYPE_LABELS[typeKey]
  const currentFile = profileData[`prompt_${typeKey}`] || ''
  const currentModel = profileData[`prompt_${typeKey}_model`] || ''
  const isUnconfigured = !currentFile

  const [promptFiles, setPromptFiles] = useState([])
  const [selectedFile, setSelectedFile] = useState(currentFile)
  const [modelOverride, setModelOverride] = useState(currentModel || (isUnconfigured ? defaultModel : ''))
  const [content, setContent] = useState('')
  const [loadingContent, setLoadingContent] = useState(false)
  const [contentError, setContentError] = useState(null)
  const [contentNotice, setContentNotice] = useState(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [saveAsOpen, setSaveAsOpen] = useState(false)
  const [saveAsName, setSaveAsName] = useState('')
  const [saveAsError, setSaveAsError] = useState(null)
  const [saveAsSubmitting, setSaveAsSubmitting] = useState(false)
  const [popOut, setPopOut] = useState(false)
  const textareaRef = useRef(null)
  const originalContent = useRef('')

  // Load file list on mount; also fetch default content when unconfigured
  useEffect(() => {
    listPrompts().then((r) => setPromptFiles(r.prompts || []))
    if (isUnconfigured) {
      setLoadingContent(true)
      getDefaultPrompt(typeKey)
        .then(({ path, content: text }) => {
          setSelectedFile(path)
          setContent(text)
          originalContent.current = text
        })
        .catch(() => { /* leave blank if no default */ })
        .finally(() => setLoadingContent(false))
    }
  }, [])

  // Escape closes the pop-out when open, otherwise closes the modal.
  useEscape(popOut, () => setPopOut(false))
  useEscape(!popOut, onClose)

  // Load file content when selection changes. If the configured file is gone
  // (e.g. it was renamed), fall back to the type's default so the editor isn't
  // left empty/errored and the user can re-link by saving.
  useEffect(() => {
    if (!selectedFile) { setContent(''); originalContent.current = ''; return }
    let cancelled = false
    ;(async () => {
      setLoadingContent(true)
      setContentError(null)
      setContentNotice(null)
      try {
        const text = await getPromptFile(selectedFile)
        if (cancelled) return
        setContent(text)
        originalContent.current = text
      } catch {
        try {
          const { content: text } = await getDefaultPrompt(typeKey)
          if (cancelled) return
          setContent(text)
          originalContent.current = text
          setContentNotice('Configured file not found — loaded the default. Pick a file or Save As to re-link.')
        } catch {
          if (!cancelled) setContentError('Could not load file')
        }
      } finally {
        if (!cancelled) setLoadingContent(false)
      }
    })()
    return () => { cancelled = true }
  }, [selectedFile])

  const handleUpload = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      const result = await uploadPromptFile(file)
      const updated = await listPrompts()
      setPromptFiles(updated.prompts || [])
      setSelectedFile(result.path)
    } catch {
      setSaveError('Upload failed')
    } finally {
      setUploading(false)
      e.target.value = ''
    }
  }

  const handleDrop = useCallback((e) => {
    e.preventDefault()
    const token = e.dataTransfer.getData('text/plain')
    if (!token || !textareaRef.current) return
    const ta = textareaRef.current
    let offset = ta.selectionStart ?? 0
    // Try to get precise drop position
    if (document.caretPositionFromPoint) {
      const pos = document.caretPositionFromPoint(e.clientX, e.clientY)
      if (pos && pos.offsetNode === ta) offset = pos.offset
    }
    const before = content.slice(0, offset)
    const after = content.slice(offset)
    const next = before + token + after
    setContent(next)
    requestAnimationFrame(() => {
      ta.focus()
      ta.setSelectionRange(offset + token.length, offset + token.length)
    })
  }, [content])

  const handleDragOver = (e) => { e.preventDefault() }

  const isDefaultPrompt = (path) => /[/\\]defaults[/\\]/.test(path)

  const [fieldErrors, setFieldErrors] = useState({})

  const handleSave = async () => {
    const fe = {}
    if (!selectedFile) fe.selectedFile = 'A prompt file must be selected'
    setFieldErrors(fe)
    if (Object.keys(fe).length > 0) return
    setSaving(true)
    setSaveError(null)
    try {
      let resolvedFile = selectedFile
      if (isDefaultPrompt(selectedFile)) {
        // Always fork defaults into a profile-specific file; never mutate defaults
        if (content !== originalContent.current || isUnconfigured) {
          const baseName = selectedFile.split(/[\\/]/).pop().replace(/\.md$/i, '')
          const filename = `${baseName}_${Date.now()}.md`
          const result = await createPromptFile(filename, content)
          resolvedFile = result.path
          originalContent.current = content
          setSelectedFile(resolvedFile)
        }
      } else if (content !== originalContent.current) {
        await putPromptFile(selectedFile, content)
        originalContent.current = content
      }
      // Patch profile with updated file ref and model
      const newData = {
        ...profileData,
        [`prompt_${typeKey}`]: resolvedFile,
        [`prompt_${typeKey}_model`]: modelOverride,
      }
      await updateProfile(profileId, { name: profileName || '', data: newData })
      onSaved(typeKey, resolvedFile, modelOverride)
      window.dispatchEvent(new CustomEvent('auto-apply:prompt-status-stale'))
      onClose()
    } catch {
      setSaveError('Save failed')
    } finally {
      setSaving(false)
    }
  }

  // Reset to the shipped default. This is the ONLY way to point a profile at a
  // defaults/ prompt: a normal Save forks defaults into a custom copy, so without
  // this the user can never select a pure default.
  const handleReset = async () => {
    setSaving(true)
    setSaveError(null)
    try {
      const { path, content: text } = await getDefaultPrompt(typeKey)
      const newData = {
        ...profileData,
        [`prompt_${typeKey}`]: path,
        [`prompt_${typeKey}_model`]: modelOverride,
      }
      await updateProfile(profileId, { name: profileName || '', data: newData })
      setSelectedFile(path)
      setContent(text)
      originalContent.current = text
      setContentError(null)
      setContentNotice(null)
      onSaved(typeKey, path, modelOverride)
      window.dispatchEvent(new CustomEvent('auto-apply:prompt-status-stale'))
      onClose()
    } catch {
      setSaveError('Reset to default failed')
    } finally {
      setSaving(false)
    }
  }

  const suggestSaveAsName = () => {
    const base = selectedFile
      ? selectedFile.split(/[\\/]/).pop().replace(/\.md$/i, '')
      : typeKey
    const isDefault = isDefaultPrompt(selectedFile)
    return isDefault ? `${base}_custom.md` : `${base}_copy.md`
  }

  const openSaveAs = () => {
    setSaveAsName(suggestSaveAsName())
    setSaveAsError(null)
    setSaveAsOpen(true)
  }

  const handleSaveAsConfirm = async () => {
    const filename = saveAsName.trim()
    if (!filename) { setSaveAsError('Filename is required'); return }
    const name = filename.endsWith('.md') ? filename : filename + '.md'
    setSaveAsSubmitting(true)
    setSaveAsError(null)
    try {
      const result = await createPromptFile(name, content)
      const updated = await listPrompts()
      setPromptFiles(updated.prompts || [])
      setSelectedFile(result.path)
      originalContent.current = content
      setSaveAsOpen(false)
      const newData = {
        ...profileData,
        [`prompt_${typeKey}`]: result.path,
        [`prompt_${typeKey}_model`]: modelOverride,
      }
      await updateProfile(profileId, { name: profileName || '', data: newData })
      onSaved(typeKey, result.path, modelOverride)
      window.dispatchEvent(new CustomEvent('auto-apply:prompt-status-stale'))
      onClose()
    } catch (e) {
      const msg = e?.message || ''
      setSaveAsError(msg.includes('409') ? 'A file with that name already exists' : 'Save failed')
    } finally {
      setSaveAsSubmitting(false)
    }
  }

  const basename = (path) => path.split(/[\\/]/).pop()

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
    if (loadingContent) return <p className="text-xs text-space-dim">Loading…</p>
    if (contentError) return <p className="text-xs text-red-400">{contentError}</p>
    return (
      <>
      {contentNotice && <p className="text-xs text-yellow-400 mb-1.5">{contentNotice}</p>}
      <textarea
        ref={textareaRef}
        rows={14}
        className={inputClass + ' resize-y font-mono text-xs ' + extraTextareaClass}
        value={content}
        onChange={(e) => setContent(e.target.value)}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        placeholder={selectedFile ? '' : 'Select a file above to edit'}
        disabled={!selectedFile}
      />
      </>
    )
  }

  // Ensure the currently-selected file is always a visible, pre-populated option,
  // even when it lives in defaults/ (not returned by listPrompts) or no longer exists.
  const fileOptions = (selectedFile && !promptFiles.some((f) => f.path === selectedFile))
    ? [{ path: selectedFile, name: basename(selectedFile) + (isDefaultPrompt(selectedFile) ? ' (default)' : '') }, ...promptFiles]
    : promptFiles

  return (
    <>
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
        <div className="bg-[#0f0f1a] border border-space-border rounded-xl w-[90%] max-w-2xl max-h-[90vh] flex flex-col shadow-2xl">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-space-border shrink-0">
            <span className="text-sm font-semibold text-space-text">{label}</span>
            <div className="flex items-center gap-3">
              <button
                onClick={handleReset}
                disabled={saving || loadingContent || isDefaultPrompt(selectedFile)}
                title={isDefaultPrompt(selectedFile) ? 'Already using the default prompt' : 'Reset to default prompt'}
                aria-label="Reset to default prompt"
                className="text-space-dim hover:text-purple-400 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M3 12a9 9 0 1 0 3-6.7L3 8" />
                  <path d="M3 3v5h5" />
                </svg>
              </button>
              <button onClick={onClose} className="text-space-dim hover:text-space-text text-lg leading-none">×</button>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-4">
            {/* Zone 1: File selector */}
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-semibold uppercase tracking-widest text-space-dim">Prompt File <span className="text-red-400">*</span></label>
              <div className="flex gap-2">
                <select
                  className={inputClass + ' flex-1'}
                  value={selectedFile}
                  onChange={(e) => { setSelectedFile(e.target.value); setFieldErrors(prev => { const n = { ...prev }; delete n.selectedFile; return n }) }}
                >
                  <option value="" style={{ color: '#000', backgroundColor: '#fff' }}>— select a file —</option>
                  {fileOptions.map((f) => (
                    <option key={f.path} value={f.path} style={{ color: '#000', backgroundColor: '#fff' }}>{f.name}</option>
                  ))}
                </select>
                <label className={`px-3 py-2 rounded-lg border border-space-border text-xs text-space-dim hover:text-space-text hover:border-purple-500/50 transition-colors cursor-pointer ${uploading ? 'opacity-50 pointer-events-none' : ''}`}>
                  {uploading ? '…' : 'Upload'}
                  <input type="file" accept=".md" className="hidden" onChange={handleUpload} />
                </label>
              </div>
              {fieldErrors.selectedFile && <div className="text-red-400 text-sm mt-1">{fieldErrors.selectedFile}</div>}
            </div>

            {/* Zone 2: Model */}
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-semibold uppercase tracking-widest text-space-dim">Model</label>
              <input
                className={inputClass}
                value={modelOverride}
                onChange={(e) => setModelOverride(e.target.value)}
                placeholder={defaultModel || 'e.g. gpt-4o-mini (leave blank to use profile default)'}
              />
            </div>

            {/* Zone 3: Chip tray (hidden while pop-out is open) */}
            {!popOut && renderChipTray()}

            {/* Zone 4: Editor (hidden while pop-out is open) */}
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
            {saveAsOpen ? (
              <div className="flex flex-col gap-2">
                {saveAsError && <p className="text-xs text-red-400">{saveAsError}</p>}
                <div className="flex gap-2 items-center">
                  <input
                    autoFocus
                    className={inputClass + ' flex-1 text-xs'}
                    value={saveAsName}
                    onChange={(e) => { setSaveAsName(e.target.value); setSaveAsError(null) }}
                    onKeyDown={(e) => { if (e.key === 'Enter') handleSaveAsConfirm(); if (e.key === 'Escape') setSaveAsOpen(false) }}
                    placeholder="filename.md"
                  />
                  <button
                    onClick={handleSaveAsConfirm}
                    disabled={saveAsSubmitting}
                    className="px-3 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white text-xs font-semibold transition-colors shrink-0"
                  >
                    {saveAsSubmitting ? '…' : 'Confirm'}
                  </button>
                  <button
                    onClick={() => setSaveAsOpen(false)}
                    className="px-3 py-2 rounded-lg border border-space-border text-xs text-space-dim hover:text-space-text transition-colors shrink-0"
                  >
                    ✕
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex gap-2">
                <button
                  onClick={openSaveAs}
                  disabled={saving || loadingContent || !!contentError}
                  className="px-3 py-2 rounded-lg border border-space-border text-xs text-space-dim hover:text-space-text disabled:opacity-50 transition-colors shrink-0"
                >
                  Save As
                </button>
                <button
                  onClick={handleSave}
                  disabled={saving || loadingContent || !!contentError}
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
            )}
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

  // Evaluator tab state
  const [evalFile, setEvalFile] = useState(profileData[`prompt_${docType}_eval`] || '')
  const [evalModel, setEvalModel] = useState(profileData[`prompt_${docType}_eval_model`] || '')
  const [evalContent, setEvalContent] = useState('')
  const [evalLoading, setEvalLoading] = useState(false)
  const [evalContentError, setEvalContentError] = useState(null)
  const evalOriginal = useRef('')
  const evalTextareaRef = useRef(null)

  // Rewriter tab state
  const [refineFile, setRefineFile] = useState(profileData[`prompt_${docType}_refine`] || '')
  const [refineModel, setRefineModel] = useState(profileData[`prompt_${docType}_refine_model`] || '')
  const [refineContent, setRefineContent] = useState('')
  const [refineLoading, setRefineLoading] = useState(false)
  const [refineContentError, setRefineContentError] = useState(null)
  const refineOriginal = useRef('')
  const refineTextareaRef = useRef(null)

  // Shared state
  const [promptFiles, setPromptFiles] = useState([])
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [popOut, setPopOut] = useState(false)
  const [saveAsOpen, setSaveAsOpen] = useState(false)
  const [saveAsName, setSaveAsName] = useState('')
  const [saveAsError, setSaveAsError] = useState(null)
  const [saveAsSubmitting, setSaveAsSubmitting] = useState(false)

  const isEval = activeTab === 'evaluator'
  const currentFile = isEval ? evalFile : refineFile
  const setCurrentFile = isEval ? setEvalFile : setRefineFile
  const currentModel = isEval ? evalModel : refineModel
  const setCurrentModel = isEval ? setEvalModel : setRefineModel
  const currentContent = isEval ? evalContent : refineContent
  const setCurrentContent = isEval ? setEvalContent : setRefineContent
  const currentLoading = isEval ? evalLoading : refineLoading
  const currentContentError = isEval ? evalContentError : refineContentError
  const currentOriginal = isEval ? evalOriginal : refineOriginal
  const currentTextareaRef = isEval ? evalTextareaRef : refineTextareaRef
  const currentTypeKey = isEval ? `${docType}_eval` : `${docType}_refine`
  const extraChips = isEval ? REFINEMENT_EVAL_CHIPS : REFINEMENT_REFINE_CHIPS

  useEscape(!popOut, onClose)
  useEscape(popOut, () => setPopOut(false))

  useEffect(() => {
    listPrompts().then(r => setPromptFiles(r.prompts || []))
  }, [])

  // Load default content if file is unset
  useEffect(() => {
    if (!evalFile) {
      setEvalLoading(true)
      getDefaultPrompt(`${docType}_eval`)
        .then(({ path, content }) => { setEvalFile(path); setEvalContent(content); evalOriginal.current = content })
        .catch(() => {})
        .finally(() => setEvalLoading(false))
    }
    if (!refineFile) {
      setRefineLoading(true)
      getDefaultPrompt(`${docType}_refine`)
        .then(({ path, content }) => { setRefineFile(path); setRefineContent(content); refineOriginal.current = content })
        .catch(() => {})
        .finally(() => setRefineLoading(false))
    }
  }, [])

  // Load content when file selection changes
  useEffect(() => {
    if (!evalFile) { setEvalContent(''); return }
    setEvalLoading(true); setEvalContentError(null)
    getPromptFile(evalFile)
      .then(t => { setEvalContent(t); evalOriginal.current = t })
      .catch(() => setEvalContentError('Could not load file'))
      .finally(() => setEvalLoading(false))
  }, [evalFile])

  useEffect(() => {
    if (!refineFile) { setRefineContent(''); return }
    setRefineLoading(true); setRefineContentError(null)
    getPromptFile(refineFile)
      .then(t => { setRefineContent(t); refineOriginal.current = t })
      .catch(() => setRefineContentError('Could not load file'))
      .finally(() => setRefineLoading(false))
  }, [refineFile])

  const isDefaultPrompt = (path) => /[/\\]defaults[/\\]/.test(path)
  const basename = (path) => path?.split(/[\\/]/).pop() ?? ''

  // Keep the active file selectable even when it lives in defaults/ (which
  // listPrompts omits) or was renamed away.
  const fileOptions = (currentFile && !promptFiles.some((f) => f.path === currentFile))
    ? [{ path: currentFile, name: basename(currentFile) + (isDefaultPrompt(currentFile) ? ' (default)' : '') }, ...promptFiles]
    : promptFiles

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

  const handleUpload = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      const result = await uploadPromptFile(file)
      const updated = await listPrompts()
      setPromptFiles(updated.prompts || [])
      setCurrentFile(result.path)
    } catch { setSaveError('Upload failed') }
    finally { setUploading(false); e.target.value = '' }
  }

  const _resolveFile = async (file, content, original, setFile) => {
    if (!file) return file
    if (isDefaultPrompt(file) && content !== original.current) {
      const baseName = basename(file).replace(/\.md$/i, '')
      const filename = `${baseName}_${Date.now()}.md`
      const result = await createPromptFile(filename, content)
      setFile(result.path)
      original.current = content
      return result.path
    } else if (!isDefaultPrompt(file) && content !== original.current) {
      await putPromptFile(file, content)
      original.current = content
    }
    return file
  }

  const handleSave = async () => {
    setSaving(true); setSaveError(null)
    try {
      const resolvedEval = await _resolveFile(evalFile, evalContent, evalOriginal, setEvalFile)
      const resolvedRefine = await _resolveFile(refineFile, refineContent, refineOriginal, setRefineFile)
      const newData = {
        ...profileData,
        [`prompt_${docType}_eval`]: resolvedEval,
        [`prompt_${docType}_eval_model`]: evalModel,
        [`prompt_${docType}_refine`]: resolvedRefine,
        [`prompt_${docType}_refine_model`]: refineModel,
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

  const openSaveAs = () => {
    const base = currentFile ? basename(currentFile).replace(/\.md$/i, '') : currentTypeKey
    setSaveAsName(isDefaultPrompt(currentFile ?? '') ? `${base}_custom.md` : `${base}_copy.md`)
    setSaveAsError(null); setSaveAsOpen(true)
  }

  const handleSaveAsConfirm = async () => {
    const filename = saveAsName.trim()
    if (!filename) { setSaveAsError('Filename is required'); return }
    const name = filename.endsWith('.md') ? filename : filename + '.md'
    setSaveAsSubmitting(true); setSaveAsError(null)
    try {
      const result = await createPromptFile(name, currentContent)
      const updated = await listPrompts()
      setPromptFiles(updated.prompts || [])
      setCurrentFile(result.path)
      currentOriginal.current = currentContent
      setSaveAsOpen(false)
    } catch (e) {
      const msg = e?.message || ''
      setSaveAsError(msg.includes('409') ? 'A file with that name already exists' : 'Save failed')
    } finally { setSaveAsSubmitting(false) }
  }

  const renderEditor = (extraClass = '') => {
    if (currentLoading) return <p className="text-xs text-space-dim">Loading…</p>
    if (currentContentError) return <p className="text-xs text-red-400">{currentContentError}</p>
    return (
      <textarea
        ref={currentTextareaRef}
        rows={12}
        className={inputClass + ' resize-y font-mono text-xs ' + extraClass}
        value={currentContent}
        onChange={e => setCurrentContent(e.target.value)}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        placeholder={currentFile ? '' : 'Select a file above to edit'}
        disabled={!currentFile}
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
      {/* File selector */}
      <div className="flex flex-col gap-1.5">
        <label className="text-xs font-semibold uppercase tracking-widest text-space-dim">Prompt File</label>
        <div className="flex gap-2">
          <select className={inputClass + ' flex-1'} value={currentFile}
            onChange={e => setCurrentFile(e.target.value)}>
            <option value="" style={{ color: '#000', backgroundColor: '#fff' }}>— select a file —</option>
            {fileOptions.map(f => (
              <option key={f.path} value={f.path} style={{ color: '#000', backgroundColor: '#fff' }}>{f.name}</option>
            ))}
          </select>
          <label className={`px-3 py-2 rounded-lg border border-space-border text-xs text-space-dim hover:text-space-text hover:border-purple-500/50 transition-colors cursor-pointer ${uploading ? 'opacity-50 pointer-events-none' : ''}`}>
            {uploading ? '…' : 'Upload'}
            <input type="file" accept=".md" className="hidden" onChange={handleUpload} />
          </label>
        </div>
      </div>
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
            {saveAsOpen ? (
              <div className="flex flex-col gap-2">
                {saveAsError && <p className="text-xs text-red-400">{saveAsError}</p>}
                <div className="flex gap-2 items-center">
                  <input autoFocus className={inputClass + ' flex-1 text-xs'} value={saveAsName}
                    onChange={e => { setSaveAsName(e.target.value); setSaveAsError(null) }}
                    onKeyDown={e => { if (e.key === 'Enter') handleSaveAsConfirm(); if (e.key === 'Escape') setSaveAsOpen(false) }}
                    placeholder="filename.md" />
                  <button onClick={handleSaveAsConfirm} disabled={saveAsSubmitting}
                    className="px-3 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white text-xs font-semibold shrink-0">
                    {saveAsSubmitting ? '…' : 'Confirm'}
                  </button>
                  <button onClick={() => setSaveAsOpen(false)}
                    className="px-3 py-2 rounded-lg border border-space-border text-xs text-space-dim hover:text-space-text shrink-0">✕</button>
                </div>
              </div>
            ) : (
              <div className="flex gap-2">
                <button onClick={openSaveAs} disabled={saving || currentLoading || !!currentContentError}
                  className="px-3 py-2 rounded-lg border border-space-border text-xs text-space-dim hover:text-space-text disabled:opacity-50 shrink-0">
                  Save As
                </button>
                <button onClick={handleSave} disabled={saving || currentLoading || !!currentContentError}
                  className="flex-1 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white text-sm font-semibold transition-colors">
                  {saving ? 'Saving…' : 'Save'}
                </button>
                <button onClick={onClose} className="px-4 py-2 rounded-lg border border-space-border text-sm text-space-dim hover:text-space-text transition-colors">
                  Cancel
                </button>
              </div>
            )}
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

  const handleSaved = (typeKey, filePath, modelOverride) => {
    onSave({
      [`prompt_${typeKey}`]: filePath,
      [`prompt_${typeKey}_model`]: modelOverride,
    })
  }

  const handleRefinementSaved = (docType, newData) => {
    onSave(newData)
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

  const basename = (path) => path?.split(/[\\/]/).pop() ?? ''
  const isDefaultPrompt = (path) => /[/\\]defaults[/\\]/.test(path)
  const truncate = (s, n = 22) => s && s.length > n ? s.slice(0, n) + '…' : s

  return (
    <>
      <AccordionSection id="prompts" title="Prompts">
        <div className="flex flex-col gap-2">

          {/* ── Standard generation prompt cards ── */}
          {PROMPT_TYPE_KEYS.map((typeKey) => {
            const filePath = data[`prompt_${typeKey}`] || ''
            const model = data[`prompt_${typeKey}_model`] || ''
            // A prompt is "Custom" only when it points at a file outside defaults/.
            // A defaults/ path means the profile is using the shipped default prompt.
            // A prompt is "Custom" only when it points at a file outside defaults/.
            // A defaults/ path means the profile is using the shipped default prompt.
            const configured = filePath && filePath.endsWith('.md') && !isDefaultPrompt(filePath)
            const bn = filePath ? basename(filePath) : null

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
                    {bn
                      ? <span className="text-xs text-space-dim truncate">{bn}</span>
                      : <span className="text-xs text-red-400/80">Not configured</span>
                    }
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
                  const evalPath = data[`prompt_${refinementDocType}_eval`] || ''
                  const refinePath = data[`prompt_${refinementDocType}_refine`] || ''
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
                          Eval: {evalPath ? truncate(basename(evalPath)) : <span className="text-space-dim/40">default</span>}
                          {evalModel ? <span className="text-purple-400/50"> · {truncate(evalModel, 16)}</span> : null}
                        </span>
                        <span className="text-xs text-space-dim/70 truncate">
                          Rewrite: {refinePath ? truncate(basename(refinePath)) : <span className="text-space-dim/40">default</span>}
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
          profileName={profileName}
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

function LlmSection({ profile, onSave }) {
  const [open, setOpen] = useState(false)
  const [providerType, setProviderType] = useState('')
  const [model, setModel] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [keyEdited, setKeyEdited] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [errors, setErrors] = useState({})

  const openModal = () => {
    setProviderType(profile.llm_provider_type || profile.data?.llm_provider_type || '')
    setModel(profile.llm_model || profile.data?.llm_model || '')
    setApiKey('')
    setKeyEdited(false)
    setError(null)
    setErrors({})
    setOpen(true)
  }

  const handleSave = async () => {
    // Validate: api_key required when no existing key or actively editing
    const needsKey = !profile.has_llm_key || keyEdited
    const errs = validateProvider({
      api_key: needsKey ? apiKey : 'placeholder',
      model,
    })
    // If key is not being changed and one already exists, skip api_key error
    if (!needsKey) delete errs.api_key
    setErrors(errs)
    if (Object.keys(errs).length > 0) return
    setSaving(true)
    try {
      await onSave({
        providerType,
        model,
        apiKey: keyEdited ? apiKey : '',
      })
      setOpen(false)
    } catch {
      setError('Save failed')
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <AccordionSection id="llm-config" title="LLM Config" editButton={<EditBtn onClick={openModal} />}>
        <div className="flex flex-col gap-1.5">
          {(profile.llm_provider_type || profile.data?.llm_provider_type)
            ? <Field label="Provider" value={profile.llm_provider_type || profile.data?.llm_provider_type} />
            : <p className="text-xs text-space-dim">No LLM provider configured.</p>
          }
          {(profile.llm_model || profile.data?.llm_model) && <Field label="Model" value={profile.llm_model || profile.data?.llm_model} />}
          <div className="flex items-center justify-between">
            <span className="text-xs text-space-dim">API Key</span>
            <span className={`text-xs font-medium ${profile.has_llm_key ? 'text-green-400' : 'text-space-dim/50'}`}>
              {profile.has_llm_key ? 'Configured' : 'Not set'}
            </span>
          </div>
        </div>
      </AccordionSection>

      {open && (
        <ItemOverlay title="LLM Config" onClose={() => setOpen(false)} onSave={handleSave} saving={saving} error={error}>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-space-dim">Provider</label>
            <select
              className={inputClass}
              value={providerType}
              onChange={e => setProviderType(e.target.value)}
            >
              <option value="">— select —</option>
              {PROVIDER_TYPES.map(p => <option key={p} value={p}>{p}</option>)}
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-space-dim">Model <span className="text-red-400">*</span><HelpIcon text="The specific model to use (e.g., claude-haiku-4-5-20251001 for Anthropic, gpt-4o-mini for OpenAI)." docHref="/docs" /></label>
            <input
              className={inputClass}
              value={model}
              onChange={e => { setModel(e.target.value); setErrors(prev => { const n = { ...prev }; delete n.model; return n }) }}
              placeholder="e.g. gpt-4o"
            />
            {errors.model && <div className="text-red-400 text-sm mt-1">{errors.model}</div>}
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-space-dim">
              API Key {(!profile.has_llm_key || keyEdited) && <span className="text-red-400">*</span>}<HelpIcon text="Your provider's secret API key. The app uses this to call the LLM on your behalf. Keep it private — never share it." docHref="/docs" />
            </label>
            <input
              type="password"
              className={inputClass}
              value={!keyEdited && profile.has_llm_key ? '••••••••' : apiKey}
              onFocus={() => { if (!keyEdited && profile.has_llm_key) { setKeyEdited(true); setApiKey('') } }}
              onChange={e => { setKeyEdited(true); setApiKey(e.target.value); setErrors(prev => { const n = { ...prev }; delete n.api_key; return n }) }}
              placeholder={profile.has_llm_key ? '' : 'Enter API key'}
            />
            {profile.has_llm_key && !keyEdited && (
              <p className="text-xs text-space-dim">Click to replace existing key</p>
            )}
            {errors.api_key && <div className="text-red-400 text-sm mt-1">{errors.api_key}</div>}
          </div>
        </ItemOverlay>
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
  prompt_scoring: '', prompt_resume: '', prompt_cover: '',
  prompt_extraction: '', prompt_resume_parse: '',
}

export default function ProfileDetailView({ profileId, onDelete }) {
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [confirmDelete, setConfirmDelete] = useState(false)
  useEscape(confirmDelete, () => setConfirmDelete(false))
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState(null)
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

  const handleSaveLlm = async ({ providerType, model, apiKey }) => {
    const newData = { ...profile.data, llm_provider_type: providerType, llm_model: model }
    const body = { name: profile.name, data: newData }
    if (apiKey) body.llm_api_key = apiKey
    await updateProfile(profileId, body)
    setProfile(p => ({ ...p, data: newData, llm_provider_type: providerType, llm_model: model, has_llm_key: apiKey ? true : p.has_llm_key }))
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

  const handleDelete = async () => {
    setDeleting(true)
    setDeleteError(null)
    try {
      await deleteProfile(profileId)
      onDelete?.()
    } catch {
      setDeleteError('Delete failed')
      setDeleting(false)
    }
  }

  if (loading) return <p className="text-xs text-space-dim">Loading…</p>
  if (error) return <p className="text-xs text-red-400">{error}</p>

  const d = profile.data

  return (
    <>
      <div className="flex flex-col gap-3">
        <IdentitySection data={d} onSave={handleSave} />
        <SkillsSection data={d} onSave={handleSave} />
        <ExperienceSection data={d} onSave={handleSave} />
        <EducationSection data={d} onSave={handleSave} />
        <ProjectsSection data={d} onSave={handleSave} />
        <JobPrefsSection data={d} onSave={handleSave} />
        <PromptsSection
          data={d}
          profileId={profileId}
          profileName={profile.name}
          defaultModel={profile.llm_model || ''}
          onSave={handleSave}
        />
        <LlmSection profile={profile} onSave={handleSaveLlm} />

        <button
          onClick={handleExportMaster}
          disabled={exporting}
          className="w-full py-2 rounded-lg border border-purple-500/30 text-sm text-purple-400 hover:bg-purple-500/10 transition-colors mt-2 disabled:opacity-50"
        >
          {exporting ? 'Generating…' : 'Export Master'}
        </button>
        {exportError && <p className="text-xs text-red-400 mt-1">{exportError}</p>}
        <button
          onClick={() => { setDeleteError(null); setConfirmDelete(true) }}
          className="w-full py-2 rounded-lg border border-red-500/30 text-sm text-red-400 hover:bg-red-500/10 transition-colors mt-2"
        >
          Delete Profile
        </button>
      </div>

      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-[#0f0f1a] border border-space-border rounded-xl w-[90%] max-w-sm p-5 flex flex-col gap-4 shadow-2xl">
            <div>
              <p className="text-sm font-semibold text-space-text">Delete profile?</p>
              <p className="text-xs text-space-dim mt-1">
                This will permanently delete <span className="text-space-text">{profile.name}</span> and cannot be undone.
              </p>
            </div>
            {deleteError && <p className="text-xs text-red-400">{deleteError}</p>}
            <div className="flex gap-2">
              <button
                onClick={handleDelete}
                disabled={deleting}
                className="flex-1 py-2 rounded-lg bg-red-600 hover:bg-red-500 disabled:opacity-50 text-white text-sm font-semibold transition-colors"
              >
                {deleting ? 'Deleting…' : 'Delete'}
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
    </>
  )
}

