import { useState } from 'react'

// Card picker that replaces the plain "+ Add section" button. Dumb/callback-
// driven: clicking a card calls onAdd(template) and collapses the panel.
export function SectionGallery({ templates, onAdd }) {
  const [open, setOpen] = useState(false)

  if (!open) {
    return (
      <button
        type="button"
        className="self-start text-xs text-purple-400 hover:text-purple-300 mt-1"
        onClick={() => setOpen(true)}
      >+ Add section</button>
    )
  }

  return (
    <div className="flex flex-col gap-2 mt-1">
      <div className="flex items-center justify-between">
        <span className="text-xs text-space-dim">Add a section</span>
        <button
          type="button" aria-label="Close section gallery"
          className="text-space-dim hover:text-space-text text-sm leading-none"
          onClick={() => setOpen(false)}
        >×</button>
      </div>
      <div className="grid grid-cols-2 gap-2">
        {templates.map((t) => (
          <button
            key={t.id} type="button"
            className="text-left border border-space-border rounded-lg p-2 hover:border-purple-400 transition-colors"
            onClick={() => { onAdd(t); setOpen(false) }}
          >
            <div className="text-sm text-space-text">{t.label}</div>
            <div className="text-xs text-space-dim">{t.description}</div>
          </button>
        ))}
      </div>
    </div>
  )
}
