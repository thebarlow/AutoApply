import { useEffect, useRef, useState } from 'react'

const inputCls =
  'w-full text-xs rounded bg-[#0a0a1a] border border-space-border text-space-text p-1.5 focus:border-purple-500 outline-none'

// Inline editor for one résumé item. Renders fields appropriate to `section`.
// Commits via the Save button, Enter (Shift+Enter inserts a newline in textareas),
// or click-out. `onCancel` is called on Escape (and on a no-op click-out).
export default function ItemEditor({ section, value, onCommit, onCancel }) {
  const [draft, setDraft] = useState(value)
  const rootRef = useRef(null)

  useEffect(() => { setDraft(value) }, [value])

  const dirty = JSON.stringify(draft) !== JSON.stringify(value)
  const commit = () => { if (dirty) onCommit(draft); else onCancel && onCancel() }
  const onBlur = (e) => {
    // Commit only when focus leaves the whole editor (not when moving between its fields).
    if (rootRef.current && !rootRef.current.contains(e.relatedTarget)) commit()
  }
  const onKeyDown = (e) => {
    if (e.key === 'Escape') { e.preventDefault(); onCancel && onCancel() }
    // Enter commits; Shift+Enter falls through to insert a newline in textareas.
    else if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); commit() }
  }

  const set = (patch) => setDraft((d) => (typeof d === 'object' ? { ...d, ...patch } : d))

  return (
    <div ref={rootRef} onBlur={onBlur} onKeyDown={onKeyDown} className="flex flex-col gap-1.5">
      {section === 'summary' && (
        <textarea autoFocus rows={4} className={inputCls}
          value={draft} onChange={(e) => setDraft(e.target.value)} />
      )}

      {section === 'experience' && (
        <>
          <input autoFocus className={inputCls} placeholder="Title"
            value={draft.title || ''} onChange={(e) => set({ title: e.target.value })} />
          <input className={inputCls} placeholder="Company"
            value={draft.company || ''} onChange={(e) => set({ company: e.target.value })} />
          <div className="flex gap-1.5">
            <input className={inputCls} placeholder="Start"
              value={draft.start || ''} onChange={(e) => set({ start: e.target.value })} />
            <input className={inputCls} placeholder="End"
              value={draft.end || ''} onChange={(e) => set({ end: e.target.value })} />
          </div>
          <textarea rows={4} className={inputCls} placeholder="Description (markdown)"
            value={draft.description || ''} onChange={(e) => set({ description: e.target.value })} />
        </>
      )}

      {section === 'education' && (
        <>
          <input autoFocus className={inputCls} placeholder="Degree"
            value={draft.degree || ''} onChange={(e) => set({ degree: e.target.value })} />
          <input className={inputCls} placeholder="Field"
            value={draft.field || ''} onChange={(e) => set({ field: e.target.value })} />
          <input className={inputCls} placeholder="Institution"
            value={draft.institution || ''} onChange={(e) => set({ institution: e.target.value })} />
          <input className={inputCls} placeholder="Graduated"
            value={draft.graduated || ''} onChange={(e) => set({ graduated: e.target.value })} />
        </>
      )}

      {section === 'project' && (
        <>
          <input autoFocus className={inputCls} placeholder="Name"
            value={draft.name || ''} onChange={(e) => set({ name: e.target.value })} />
          <input className={inputCls} placeholder="URL"
            value={draft.url || ''} onChange={(e) => set({ url: e.target.value })} />
          <textarea rows={3} className={inputCls} placeholder="Description"
            value={draft.description || ''} onChange={(e) => set({ description: e.target.value })} />
        </>
      )}

      {section === 'skills' && (
        <>
          <input autoFocus className={inputCls} placeholder="Category"
            value={draft.category || ''} onChange={(e) => set({ category: e.target.value })} />
          <input className={inputCls} placeholder="Items (comma separated)"
            value={(draft.items || []).join(', ')}
            onChange={(e) => set({ items: e.target.value.split(',').map((s) => s.trim()).filter(Boolean) })} />
        </>
      )}

      <div className="flex justify-end">
        <button
          type="button"
          onClick={commit}
          disabled={!dirty}
          className="px-3 py-1 rounded text-xs font-semibold bg-purple-600 hover:bg-purple-500 text-white transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Save
        </button>
      </div>
    </div>
  )
}
