import { useState } from 'react'

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
  return (
    <textarea
      className={`${inputClass} min-h-[80px] resize-y`} value={value ?? ''}
      onChange={(e) => onChange(e.target.value)}
    />
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
  const add = () => {
    const t = draft.trim()
    if (!t) return
    onChange([...arr, t])
    setDraft('')
  }
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-1.5">
        {arr.map((tag, i) => (
          <span
            key={i}
            className="inline-flex items-center gap-1 bg-purple-500/15 text-purple-200 text-xs rounded-full px-2 py-0.5"
          >
            {tag}
            <button
              type="button" aria-label={`Remove ${tag}`}
              className="hover:text-red-300"
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
