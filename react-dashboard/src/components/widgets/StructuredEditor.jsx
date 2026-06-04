import { useEffect, useState, useCallback } from 'react'
import { getDocument, putDocument } from '../../api'

// module-level counter for stable client-side list keys
let _keySeq = 0
const nextKey = () =>
  (typeof crypto !== 'undefined' && crypto.randomUUID) ? crypto.randomUUID() : `k${++_keySeq}`

// list fields that hold arrays of objects needing stable keys
const LIST_FIELDS = ['experience', 'projects', 'skills', 'education']

// attach a stable _key to each item of every list field on load
function withKeys(doc) {
  if (!doc) return doc
  const out = { ...doc }
  for (const f of LIST_FIELDS) {
    if (Array.isArray(out[f])) {
      out[f] = out[f].map((it) =>
        (it && typeof it === 'object') ? { _key: nextKey(), ...it } : it
      )
    }
  }
  return out
}

// clone doc and strip _key from every list item before saving
function stripKeys(doc) {
  if (!doc) return doc
  const out = { ...doc }
  for (const f of LIST_FIELDS) {
    if (Array.isArray(out[f])) {
      out[f] = out[f].map((it) => {
        if (it && typeof it === 'object' && '_key' in it) {
          const { _key, ...rest } = it
          return rest
        }
        return it
      })
    }
  }
  return out
}

// ── small field helpers ──────────────────────────────────────────────
function Text({ label, value, onChange, area }) {
  const Cmp = area ? 'textarea' : 'input'
  return (
    <label className="flex flex-col gap-1 text-xs">
      <span className="text-space-dim">{label}</span>
      <Cmp
        className="bg-space-bg border border-space-border rounded px-2 py-1 text-space-text text-sm"
        rows={area ? 4 : undefined}
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  )
}

// ── résumé sections ──────────────────────────────────────────────────
function HeaderForm({ header, onChange }) {
  const set = (k) => (v) => onChange({ ...header, [k]: v })
  return (
    <div className="grid grid-cols-2 gap-2">
      {['name', 'email', 'phone', 'location', 'github', 'linkedin', 'website'].map((k) => (
        <Text key={k} label={k} value={header[k]} onChange={set(k)} />
      ))}
    </div>
  )
}

function ExperienceForm({ items, onChange }) {
  const setItem = (i, patch) => onChange(items.map((it, j) => (j === i ? { ...it, ...patch } : it)))
  return (
    <div className="flex flex-col gap-3">
      {items.map((e, i) => (
        <div key={e._key} className="border border-space-border rounded p-2 flex flex-col gap-2">
          <div className="grid grid-cols-2 gap-2">
            <Text label="title" value={e.title} onChange={(v) => setItem(i, { title: v })} />
            <Text label="company" value={e.company} onChange={(v) => setItem(i, { company: v })} />
            <Text label="start" value={e.start} onChange={(v) => setItem(i, { start: v })} />
            <Text label="end" value={e.end} onChange={(v) => setItem(i, { end: v })} />
          </div>
          <Text area label="description (Markdown)" value={e.description} onChange={(v) => setItem(i, { description: v })} />
        </div>
      ))}
    </div>
  )
}

function ProjectsForm({ items, onChange }) {
  const setItem = (i, patch) => onChange(items.map((it, j) => (j === i ? { ...it, ...patch } : it)))
  const move = (i, d) => {
    const j = i + d
    if (j < 0 || j >= items.length) return
    const next = items.slice()
    ;[next[i], next[j]] = [next[j], next[i]]
    onChange(next)
  }
  const remove = (i) => onChange(items.filter((_, j) => j !== i))
  return (
    <div className="flex flex-col gap-3">
      {items.map((p, i) => (
        <div key={p._key} className="border border-space-border rounded p-2 flex flex-col gap-2">
          <div className="grid grid-cols-2 gap-2">
            <Text label="name" value={p.name} onChange={(v) => setItem(i, { name: v })} />
            <Text label="url" value={p.url} onChange={(v) => setItem(i, { url: v })} />
          </div>
          <Text area label="description (Markdown)" value={p.description} onChange={(v) => setItem(i, { description: v })} />
          <div className="flex gap-2 text-xs">
            <button onClick={() => move(i, -1)} className="text-space-dim hover:text-space-text">↑</button>
            <button onClick={() => move(i, 1)} className="text-space-dim hover:text-space-text">↓</button>
            <button onClick={() => remove(i)} className="text-red-400 hover:text-red-300">remove</button>
          </div>
        </div>
      ))}
    </div>
  )
}

function SkillsForm({ groups, onChange }) {
  const setGroup = (i, patch) => onChange(groups.map((g, j) => (j === i ? { ...g, ...patch } : g)))
  const add = () => onChange([...groups, { _key: nextKey(), category: '', items: [] }])
  const remove = (i) => onChange(groups.filter((_, j) => j !== i))
  return (
    <div className="flex flex-col gap-2">
      {groups.map((g, i) => (
        <div key={g._key} className="grid grid-cols-2 gap-2 items-end">
          <Text label="category" value={g.category} onChange={(v) => setGroup(i, { category: v })} />
          <Text
            label="items (comma-separated)"
            value={(g.items || []).join(', ')}
            onChange={(v) => setGroup(i, { items: v.split(',').map((s) => s.trim()).filter(Boolean) })}
          />
          <button onClick={() => remove(i)} className="text-red-400 text-xs col-span-2 text-left">remove group</button>
        </div>
      ))}
      <button onClick={add} className="text-space-dim hover:text-space-text text-xs text-left">+ add group</button>
    </div>
  )
}

function EducationForm({ items, onChange }) {
  const setItem = (i, patch) => onChange(items.map((it, j) => (j === i ? { ...it, ...patch } : it)))
  return (
    <div className="flex flex-col gap-2">
      {items.map((ed, i) => (
        <div key={ed._key} className="grid grid-cols-2 gap-2">
          <Text label="institution" value={ed.institution} onChange={(v) => setItem(i, { institution: v })} />
          <Text label="degree" value={ed.degree} onChange={(v) => setItem(i, { degree: v })} />
          <Text label="field" value={ed.field} onChange={(v) => setItem(i, { field: v })} />
          <Text label="graduated" value={ed.graduated} onChange={(v) => setItem(i, { graduated: v })} />
        </div>
      ))}
    </div>
  )
}

function Section({ title, children }) {
  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs font-semibold uppercase tracking-widest text-space-dim">{title}</p>
      {children}
    </div>
  )
}

// ── the overlay ──────────────────────────────────────────────────────
export default function StructuredEditOverlay({ job, docType, onClose, onSaved }) {
  const [doc, setDoc] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [dirty, setDirty] = useState(false)

  useEffect(() => {
    let alive = true
    setLoading(true); setError(null)
    getDocument(job.job_key, docType)
      .then((d) => { if (alive) { setDoc(withKeys(d)); setDirty(false); setLoading(false) } })
      .catch((e) => { if (alive) { setError(e?.message || 'Load failed'); setLoading(false) } })
    return () => { alive = false }
  }, [job.job_key, docType])

  const patch = useCallback((p) => {
    setDoc((d) => ({ ...d, ...p }))
    setDirty(true)
  }, [])

  const requestClose = useCallback(() => {
    if (dirty && !window.confirm('Discard unsaved changes?')) return
    onClose()
  }, [dirty, onClose])

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') requestClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [requestClose])

  const handleSave = async () => {
    setSaving(true); setError(null)
    try {
      await putDocument(job.job_key, docType, stripKeys(doc))
      onSaved?.()
      onClose()
    } catch (e) {
      setError(e?.message || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-6" onClick={requestClose}>
      <div className="bg-space-panel border border-space-border rounded-xl w-full max-w-2xl max-h-[85vh] overflow-y-auto p-4 flex flex-col gap-4"
           onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-space-text">Edit {docType}</h3>
          <button onClick={requestClose} className="text-space-dim hover:text-space-text">✕</button>
        </div>
        {loading && <p className="text-xs text-space-dim">Loading…</p>}
        {error && <p className="text-xs text-red-400 break-words">{error}</p>}
        {doc && docType === 'resume' && (
          <>
            <Section title="Header"><HeaderForm header={doc.header || {}} onChange={(h) => patch({ header: h })} /></Section>
            <Section title="Profile Summary">
              <Text area label="" value={doc.profile_summary} onChange={(v) => patch({ profile_summary: v })} />
            </Section>
            <Section title="Experience"><ExperienceForm items={doc.experience || []} onChange={(x) => patch({ experience: x })} /></Section>
            <Section title="Education"><EducationForm items={doc.education || []} onChange={(x) => patch({ education: x })} /></Section>
            <Section title="Projects"><ProjectsForm items={doc.projects || []} onChange={(x) => patch({ projects: x })} /></Section>
            <Section title="Skills"><SkillsForm groups={doc.skills || []} onChange={(x) => patch({ skills: x })} /></Section>
          </>
        )}
        {doc && docType === 'cover' && (
          <>
            <Section title="Header"><HeaderForm header={doc.header || {}} onChange={(h) => patch({ header: h })} /></Section>
            <Section title="Body (Markdown)">
              <Text area label="" value={doc.body} onChange={(v) => patch({ body: v })} />
            </Section>
            <Section title="Sign-off">
              <Text label="name" value={doc.signoff?.name} onChange={(v) => patch({ signoff: { ...(doc.signoff || {}), name: v } })} />
            </Section>
          </>
        )}
        <div className="flex gap-2 justify-end">
          <button onClick={requestClose} className="px-3 py-1 rounded text-xs border border-space-border text-space-dim hover:text-space-text">Cancel</button>
          <button onClick={handleSave} disabled={saving || !doc || !dirty}
                  className="px-3 py-1 rounded text-xs bg-purple-600 hover:bg-purple-500 text-white disabled:opacity-50">
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}
