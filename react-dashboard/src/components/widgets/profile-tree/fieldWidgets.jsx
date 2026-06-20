import { useState, useEffect, useCallback } from 'react'
import { getSkillAliases, assignSkillAlias, removeSkillAliasMember } from '../../../api'

const inputClass =
  'w-full bg-white/5 border border-space-border rounded-lg px-3 py-2 text-sm text-space-text placeholder-space-dim focus:outline-none focus:border-purple-500 transition-colors'

export function TextField({ value, onChange }) {
  return (
    <input
      type="text" className={inputClass} value={value ?? ''}
      onChange={(e) => onChange(e.target.value)}
    />
  )
}

export function MarkdownField({ value, onChange }) {
  const [popOut, setPopOut] = useState(false)
  return (
    <div className="flex items-start gap-1.5">
      <textarea
        className={`${inputClass} min-h-[80px] resize-y`} value={value ?? ''}
        onChange={(e) => onChange(e.target.value)}
      />
      <button
        type="button" aria-label="Expand field editor" title="Pop out"
        className="px-1.5 py-0.5 text-space-dim hover:text-space-text"
        onClick={() => setPopOut(true)}
      >⤢</button>
      {popOut && (
        <div className="fixed inset-0 z-[160] flex items-center justify-center bg-black/60" onClick={() => setPopOut(false)}>
          <div
            className="bg-[#0f0f1a] border border-space-border rounded-2xl p-5 w-[48rem] max-w-[92vw] flex flex-col gap-3"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-end">
              <button
                type="button" aria-label="Close field editor" onClick={() => setPopOut(false)}
                className="text-space-dim hover:text-space-text text-xl leading-none"
              >×</button>
            </div>
            <textarea
              aria-label="Expanded field editor" rows={16} value={value ?? ''}
              className="bg-white/5 border border-space-border rounded px-3 py-2 text-sm text-space-text resize-y"
              onChange={(e) => onChange(e.target.value)}
            />
          </div>
        </div>
      )}
    </div>
  )
}

export function BulletsField({ value, onChange }) {
  const arr = Array.isArray(value) ? value : []
  const setAt = (i, v) => onChange(arr.map((x, j) => (j === i ? v : x)))
  const removeAt = (i) => onChange(arr.filter((_, j) => j !== i))
  return (
    <div className="flex flex-col gap-2">
      {arr.map((line, i) => (
        <div key={i} className="flex items-center gap-2">
          <input
            type="text" className={inputClass} value={line}
            onChange={(e) => setAt(i, e.target.value)}
          />
          <button
            type="button" aria-label={`Remove bullet ${i + 1}`}
            className="text-space-dim hover:text-red-400 px-1"
            onClick={() => removeAt(i)}
          >✕</button>
        </div>
      ))}
      <button
        type="button"
        className="self-start text-xs text-purple-400 hover:text-purple-300"
        onClick={() => onChange([...arr, ''])}
      >+ Add bullet</button>
    </div>
  )
}

export function TagListField({ value, onChange }) {
  const arr = Array.isArray(value) ? value : []
  const [draft, setDraft] = useState('')
  const [editIdx, setEditIdx] = useState(null)
  const add = () => {
    const t = draft.trim()
    if (!t) return
    onChange([...arr, t])
    setDraft('')
  }
  const rename = (i, name) => {
    const t = name.trim()
    if (t) onChange(arr.map((x, j) => (j === i ? t : x)))
  }
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-1.5">
        {arr.map((tag, i) => (
          <span
            key={i}
            className="inline-flex items-center gap-1 bg-purple-500/15 text-purple-200 text-xs rounded-full pl-2 pr-1 py-0.5"
          >
            <button
              type="button" title="Edit tag / aliases"
              className="hover:text-purple-100 transition-colors"
              onClick={() => setEditIdx(i)}
            >{tag}</button>
            <button
              type="button" aria-label={`Remove ${tag}`}
              className="hover:text-red-300 px-0.5"
              onClick={() => onChange(arr.filter((_, j) => j !== i))}
            >✕</button>
          </span>
        ))}
      </div>
      <input
        type="text" className={inputClass} placeholder="Add…" value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); add() } }}
        onBlur={add}
      />
      {editIdx !== null && arr[editIdx] !== undefined && (
        <TagChipModal
          tag={arr[editIdx]}
          onRename={(name) => rename(editIdx, name)}
          onClose={() => setEditIdx(null)}
        />
      )}
    </div>
  )
}

// Modal opened by clicking a tag chip: rename the focused term and manage the
// chip's alias group via the skills alias backend. The ✕ on a chip still
// deletes it (handled in TagListField); this modal never deletes the chip.
//
// `subject` is the term the Name field edits; `canonical` is the alias group's
// anchor (initially the chip itself). Clicking an alias swaps `subject` to it so
// it can be renamed in place. Renaming the canonical migrates the whole group to
// the new name and updates the field-value chip via `onRename`.
export function TagChipModal({ tag, onRename, onClose }) {
  const [canonical, setCanonical] = useState(tag)
  const [subject, setSubject] = useState(tag)
  const [name, setName] = useState(tag)
  const [members, setMembers] = useState(null)
  const [aliasDraft, setAliasDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const isCanonical = subject.toLowerCase() === canonical.toLowerCase()

  const loadMembers = useCallback(async (anchor) => {
    try {
      const { groups } = await getSkillAliases()
      const g = (groups || []).find(
        (x) => x.canonical.toLowerCase() === anchor.toLowerCase(),
      )
      setMembers(g ? g.members.filter((m) => m !== g.canonical.toLowerCase()) : [])
    } catch {
      setError('Could not load aliases')
      setMembers([])
    }
  }, [])

  useEffect(() => { loadMembers(canonical) }, [canonical, loadMembers])

  // Switch the Name field to edit an alias member (so the user can rename it).
  const focusAlias = (member) => {
    setSubject(member)
    setName(member)
  }

  const addAlias = async () => {
    const a = aliasDraft.trim()
    if (!a) return
    setBusy(true); setError(null)
    try {
      const { canonical: c, members: m } = await assignSkillAlias(a, canonical)
      setMembers((m || []).filter((x) => x !== c.toLowerCase()))
      setAliasDraft('')
    } catch {
      setError('Could not add alias')
    } finally { setBusy(false) }
  }

  const removeAlias = async (member) => {
    setBusy(true); setError(null)
    try {
      await removeSkillAliasMember(member)
      if (subject.toLowerCase() === member.toLowerCase()) {
        setSubject(canonical); setName(canonical)
      }
      await loadMembers(canonical)
    } catch {
      setError('Could not remove alias')
    } finally { setBusy(false) }
  }

  const saveName = async () => {
    const t = name.trim()
    if (!t || t === subject) return
    setBusy(true); setError(null)
    try {
      if (isCanonical) {
        // Re-key the whole group (canonical + every member) to the new name,
        // then rename the field-value chip.
        for (const token of [canonical, ...(members || [])]) {
          await assignSkillAlias(token, t)
        }
        onRename(t)
        setCanonical(t); setSubject(t)
      } else {
        // Rename a single alias member in place.
        await removeSkillAliasMember(subject)
        await assignSkillAlias(t, canonical)
        setSubject(t)
        await loadMembers(canonical)
      }
    } catch {
      setError('Could not rename')
    } finally { setBusy(false) }
  }

  return (
    <div
      className="fixed inset-0 z-[150] flex items-center justify-center bg-black/70"
      onClick={onClose}
    >
      <div
        className="bg-[#0f0f1a] border border-space-border rounded-2xl p-6 w-[24rem] max-w-[90vw]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-space-text">Edit tag</h2>
          <button
            type="button" onClick={onClose}
            className="text-space-dim hover:text-space-text text-xl leading-none"
          >×</button>
        </div>

        <label className="text-xs text-space-dim">
          {isCanonical ? 'Name' : `Renaming alias of “${canonical}”`}
        </label>
        <div className="flex gap-2 mt-1 mb-4">
          <input
            type="text" className={inputClass} value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') saveName() }}
          />
          <button
            type="button" onClick={saveName} disabled={busy}
            className="px-3 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white text-sm font-semibold transition-colors"
          >Save</button>
        </div>

        <label className="text-xs text-space-dim">Aliases</label>
        <div className="flex flex-wrap gap-1.5 mt-1 mb-2 min-h-[1.5rem]">
          {members == null && <span className="text-xs text-space-dim">Loading…</span>}
          {members && members.length === 0 && (
            <span className="text-xs text-space-dim">No aliases yet.</span>
          )}
          {(members || []).map((m) => (
            <span
              key={m}
              className={`inline-flex items-center gap-1 text-xs rounded-full px-2 py-0.5 ${
                subject.toLowerCase() === m.toLowerCase()
                  ? 'bg-purple-500/25 text-purple-100'
                  : 'bg-white/5 text-space-text'
              }`}
            >
              <button
                type="button" title="Rename this alias"
                className="hover:text-purple-200 transition-colors"
                onClick={() => focusAlias(m)}
              >{m}</button>
              <button
                type="button" aria-label={`Remove alias ${m}`} disabled={busy}
                className="hover:text-red-300 px-0.5 disabled:opacity-50"
                onClick={() => removeAlias(m)}
              >✕</button>
            </span>
          ))}
        </div>
        <div className="flex gap-2">
          <input
            type="text" className={inputClass} placeholder="Add alias…" value={aliasDraft}
            onChange={(e) => setAliasDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addAlias() } }}
          />
          <button
            type="button" onClick={addAlias} disabled={busy}
            className="px-3 py-2 rounded-lg border border-space-border text-sm text-space-dim hover:text-space-text disabled:opacity-50 transition-colors"
          >Add</button>
        </div>
        {error && <p className="text-xs text-red-400 mt-2">{error}</p>}
      </div>
    </div>
  )
}

export function FieldWidget({ field, onChange }) {
  switch (field.kind) {
    case 'markdown': return <MarkdownField value={field.value} onChange={onChange} />
    case 'bullets': return <BulletsField value={field.value} onChange={onChange} />
    case 'taglist': return <TagListField value={field.value} onChange={onChange} />
    case 'text':
    default: return <TextField value={field.value} onChange={onChange} />
  }
}
