import { useEffect, useRef, useState } from 'react'

// Cover-letter view: click the body to edit it; saves on click-out via onSave(body).
export default function CoverView({ doc, onSave, feedback, setFeedback, escapeRef }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const ref = useRef(null)

  useEffect(() => { setDraft(doc?.body || '') }, [doc])

  // Let the modal's Escape handler discard an in-progress body edit before it
  // falls back to closing the modal.
  useEffect(() => {
    if (!escapeRef) return undefined
    escapeRef.current = () => {
      if (editing) { setDraft(doc?.body || ''); setEditing(false); return true }
      return false
    }
    return () => { if (escapeRef) escapeRef.current = null }
  }, [escapeRef, editing, doc])

  if (!doc) return null

  if (editing) {
    return (
      <textarea
        ref={ref}
        autoFocus
        className="w-full h-[60vh] text-sm rounded bg-[#0a0a1a] border border-space-border text-space-text p-3 focus:border-purple-500 outline-none"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={async () => { await onSave(draft); setEditing(false) }}
        onKeyDown={(e) => { if (e.key === 'Escape') { setDraft(doc.body || ''); setEditing(false) } }}
      />
    )
  }
  return (
    <div className="flex flex-col gap-4">
      <div
        className="text-sm whitespace-pre-wrap text-space-text px-2 cursor-text rounded hover:bg-white/5 p-2"
        onClick={() => setEditing(true)}
        title="Click to edit"
      >
        {doc.body}
      </div>
      <div className="flex flex-col gap-1">
        <p className="text-xs font-semibold uppercase tracking-widest text-space-dim">Feedback for regeneration</p>
        <textarea
          rows={3}
          placeholder="What should change?"
          value={feedback}
          onChange={(e) => setFeedback(e.target.value)}
          className="w-full text-xs rounded bg-[#0a0a1a] border border-space-border text-space-text p-2 focus:border-purple-500 outline-none"
        />
      </div>
    </div>
  )
}
