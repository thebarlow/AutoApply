import { useEffect, useRef, useState } from 'react'

// Cover-letter view: click the body to edit it; saves on click-out via onSave(body).
export default function CoverView({ doc, onSave }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const ref = useRef(null)

  useEffect(() => { setDraft(doc?.body || '') }, [doc])

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
    <div
      className="text-sm whitespace-pre-wrap text-space-text px-2 cursor-text rounded hover:bg-white/5 p-2"
      onClick={() => setEditing(true)}
      title="Click to edit"
    >
      {doc.body}
    </div>
  )
}
